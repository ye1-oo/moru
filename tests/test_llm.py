from types import SimpleNamespace

from pydantic import BaseModel

from moru import config, llm


class Answer(BaseModel):
    value: int


def setup(monkeypatch, tmp_path, outputs):
    monkeypatch.setattr(config, "CACHE_DIR", tmp_path)
    monkeypatch.setattr(config, "LLM_CACHE_DIR", tmp_path / "llm")
    monkeypatch.setattr(config, "LLM_LOG", tmp_path / "calls.jsonl")
    monkeypatch.setattr(config, "GEMINI_RPM", 1e6)
    calls = []

    def fake_send(prompt, schema, video, temperature):
        calls.append(prompt)
        usage = SimpleNamespace(total_input_tokens=1, total_output_tokens=1, total_thought_tokens=0)
        return SimpleNamespace(output_text=outputs[len(calls) - 1], usage=usage)

    monkeypatch.setattr(llm, "_send", fake_send)
    return calls


def test_second_call_uses_cache(monkeypatch, tmp_path):
    calls = setup(monkeypatch, tmp_path, ['{"value": 1}'])
    assert llm.generate("q", schema=Answer).value == 1
    assert llm.generate("q", schema=Answer).value == 1
    assert len(calls) == 1
    assert llm.calls_today() == 1


def test_repeat_is_cached_separately(monkeypatch, tmp_path):
    calls = setup(monkeypatch, tmp_path, ["a", "b"])
    assert llm.generate("q", repeat=0) == "a"
    assert llm.generate("q", repeat=1) == "b"
    assert len(calls) == 2


def test_invalid_output_is_retried(monkeypatch, tmp_path):
    calls = setup(monkeypatch, tmp_path, ["not json", '{"value": 2}'])
    assert llm.generate("q", schema=Answer).value == 2
    assert len(calls) == 2


def test_daily_limit_stops(monkeypatch, tmp_path):
    setup(monkeypatch, tmp_path, ["a"])
    monkeypatch.setattr(config, "GEMINI_RPD", 1)
    assert llm.generate("q") == "a"
    try:
        llm.generate("other")
    except llm.DailyQuotaExceeded:
        return
    raise AssertionError("일일 한도에서 멈춰야 합니다")


class Failure(Exception):
    def __init__(self, status, message):
        super().__init__(message)
        self.status_code = status


def fail_with(monkeypatch, tmp_path, error):
    setup(monkeypatch, tmp_path, [])
    monkeypatch.setattr(llm, "API_ERRORS", (Failure,))
    monkeypatch.setattr(llm, "BACKOFF_SECONDS", (0, 0))
    attempts = []

    def fake_send(*args):
        attempts.append(1)
        raise error

    monkeypatch.setattr(llm, "_send", fake_send)
    return attempts


def test_daily_429_stops_without_retry(monkeypatch, tmp_path):
    error = Failure(429, "limit: 20 requests per day on Free Tier")
    attempts = fail_with(monkeypatch, tmp_path, error)
    try:
        llm.generate("q")
    except llm.DailyQuotaExceeded:
        assert len(attempts) == 1
        return
    raise AssertionError("일일 한도 오류여야 합니다")


def test_busy_server_gives_up_after_two_retries(monkeypatch, tmp_path):
    attempts = fail_with(monkeypatch, tmp_path, Failure(503, "high demand"))
    try:
        llm.generate("q")
    except llm.ServerBusy:
        assert len(attempts) == 3
        return
    raise AssertionError("과부하 오류여야 합니다")
