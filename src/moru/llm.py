"""Gemini 호출 래퍼: 디스크 캐시, 요청 간격, 재시도, 호출 수·토큰 로그.

- 프롬프트, 스키마, 영상 내용이 같으면 API를 다시 부르지 않는다.
- store=False로 Interactions 저장을 끈다. 업로드한 영상은 호출 후 바로 지운다.
- 일일 한도에 닿으면 DailyQuotaExceeded로 멈춘다. 다시 실행하면 캐시 덕분에 이어서 진행된다.
"""

import hashlib
import json
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import TypeVar
from zoneinfo import ZoneInfo

from google import genai
from google.genai import errors, types
from google.genai._gaos.lib import compat_errors  # Interactions API가 내는 오류
from pydantic import BaseModel, ValidationError

from moru import config

T = TypeVar("T", bound=BaseModel)
PACIFIC = ZoneInfo("America/Los_Angeles")  # 일일 한도는 태평양 시간 자정에 초기화된다
BACKOFF_SECONDS = (60, 180)  # 실패한 요청도 일일 한도를 쓰는 것으로 보여 적게 재시도한다
RETRYABLE = {429, 500, 502, 503, 504}
API_ERRORS = (errors.APIError, compat_errors.APIError)

_client: genai.Client | None = None
_last_call = 0.0


class DailyQuotaExceeded(RuntimeError):
    """오늘 쓸 수 있는 요청을 다 썼다."""


class ServerBusy(RuntimeError):
    """서버 과부하가 이어진다. 한도를 낭비하지 않도록 멈추고 나중에 다시 실행한다."""


def client() -> genai.Client:
    global _client
    if _client is None:
        # SDK의 자동 재시도는 보이지 않게 한도를 소모하므로 끈다.
        options = types.HttpOptions(retry_options=types.HttpRetryOptions(attempts=1))
        _client = genai.Client(http_options=options)
    return _client


def _log(**record) -> None:
    config.CACHE_DIR.mkdir(exist_ok=True)
    record["time"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    with config.LLM_LOG.open("a", encoding="utf-8") as file:
        file.write(json.dumps(record, ensure_ascii=False) + "\n")


def calls_today() -> int:
    """태평양 시간 기준 오늘 실제로 보낸 요청 수."""
    if not config.LLM_LOG.exists():
        return 0
    today = datetime.now(PACIFIC).date()
    count = 0
    for line in config.LLM_LOG.read_text(encoding="utf-8").splitlines():
        record = json.loads(line)
        sent = datetime.fromisoformat(record["time"]).astimezone(PACIFIC).date()
        count += sent == today and not record.get("cached", False)
    return count


def _wait_for_slot() -> None:
    global _last_call
    if calls_today() >= config.GEMINI_RPD:
        raise DailyQuotaExceeded(f"오늘 {config.GEMINI_RPD}회를 모두 사용했습니다")
    wait = 60 / config.GEMINI_RPM - (time.monotonic() - _last_call)
    if wait > 0:
        time.sleep(wait)
    _last_call = time.monotonic()


def _status(error: Exception) -> int | None:
    return getattr(error, "code", None) or getattr(error, "status_code", None)


def _is_daily_quota(error: Exception) -> bool:
    return _status(error) == 429 and bool(re.search(r"per day|PerDay", str(error)))


def _upload(path: Path) -> object:
    with path.open("rb") as stream:
        file = client().files.upload(file=stream, config={"mime_type": "video/mp4"})
    while not file.state or file.state.name != "ACTIVE":
        if file.state and file.state.name == "FAILED":
            raise RuntimeError(f"영상 처리 실패: {path.name}")
        time.sleep(3)
        file = client().files.get(name=file.name)
    return file


def _send(prompt: str, schema: type[BaseModel] | None, video: Path | None, temperature: float | None):
    generation_config: dict = {"thinking_level": config.THINKING_LEVEL}
    if temperature is not None:
        generation_config["temperature"] = temperature
    request: dict = {
        "model": config.GEMINI_MODEL,
        "store": False,
        "generation_config": generation_config,
    }
    if schema is not None:
        request["response_format"] = {
            "type": "text",
            "mime_type": "application/json",
            "schema": schema.model_json_schema(),
        }

    uploaded = None
    try:
        if video is None:
            request["input"] = prompt
        else:
            uploaded = _upload(video)
            request["input"] = [
                {"type": "video", "uri": uploaded.uri, "mime_type": uploaded.mime_type},
                {"type": "text", "text": prompt},
            ]
        return client().interactions.create(**request)
    finally:
        if uploaded is not None:
            client().files.delete(name=uploaded.name)


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def generate(
    prompt: str,
    *,
    schema: type[T] | None = None,
    video: Path | None = None,
    temperature: float | None = 0.0,
    repeat: int = 0,
    tag: str = "",
) -> T | str:
    """모델을 호출한다. schema를 주면 검증된 객체를, 아니면 문자열을 돌려준다.

    repeat는 같은 입력을 반복 실험할 때 캐시를 구분하는 번호다.
    """
    key_source = {
        "model": config.GEMINI_MODEL,
        "prompt": prompt,
        "schema": schema.model_json_schema() if schema else None,
        "video": _digest(video) if video else None,
        "temperature": temperature,
        "thinking": config.THINKING_LEVEL,
        "repeat": repeat,
    }
    key = hashlib.sha256(json.dumps(key_source, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
    path = config.LLM_CACHE_DIR / f"{key}.json"

    if path.exists():
        text = json.loads(path.read_text(encoding="utf-8"))["text"]
        _log(tag=tag, cached=True)
        return schema.model_validate_json(text) if schema else text

    invalid = 0
    attempt = 0
    while True:
        _wait_for_slot()
        started = time.monotonic()
        try:
            response = _send(prompt, schema, video, temperature)
        except API_ERRORS as error:
            status = _status(error)
            _log(tag=tag, cached=False, error=status)
            if _is_daily_quota(error):
                raise DailyQuotaExceeded(str(error)) from error
            if status not in RETRYABLE:
                raise
            if attempt >= len(BACKOFF_SECONDS):
                raise ServerBusy(str(error)) from error
            time.sleep(BACKOFF_SECONDS[attempt])
            attempt += 1
            continue

        usage = response.usage
        _log(
            tag=tag,
            cached=False,
            seconds=round(time.monotonic() - started, 1),
            input_tokens=getattr(usage, "total_input_tokens", None),
            output_tokens=getattr(usage, "total_output_tokens", None),
            thought_tokens=getattr(usage, "total_thought_tokens", None),
        )
        text = response.output_text
        try:
            result = schema.model_validate_json(text) if schema else text
        except ValidationError:
            invalid += 1
            if invalid > config.MAX_RETRIES:
                raise
            continue

        config.LLM_CACHE_DIR.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"text": text}, ensure_ascii=False), encoding="utf-8")
        return result
