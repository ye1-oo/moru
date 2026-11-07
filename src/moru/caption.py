"""영상 + K-DST 문항으로 행동 중심 캡션을 만든다 (명세 4.1). 부모 일기는 넣지 않는다.

item_conditioned 모드는 6개 영역 문항을 모두 넣는다. 해당 영역 문항만 넣으면
캡션에 정답 영역이 새어 들어가 실험 A의 비교가 무의미해지기 때문이다.
"""

import hashlib
import json
import re
import unicodedata
from pathlib import Path

import pandas as pd

from moru import config, llm
from moru.schemas import Caption, CaptionBatch, CaptionMode, KdstItem

BATCH_HEAD = """당신은 영유아 영상을 객관적으로 기록하는 관찰자입니다.
[영상 N]으로 표시된 영상마다, 아이가 실제로 한 행동을 한국어 문장 3~6개로 묘사하세요.
영상은 서로 관련이 없습니다. 영상마다 따로 보고, 다른 영상의 내용을 섞거나 비교하지 않습니다."""

# 앞의 18개를 1개씩 캡셔닝할 때 쓴 머리말. 단독 호출은 이 문장을 그대로 써야 비교가 맞는다.
SINGLE_HEAD = """당신은 영유아 영상을 객관적으로 기록하는 관찰자입니다.
영상에서 아이가 실제로 한 행동을 한국어 문장 3~6개로 묘사하세요."""

RULES = """
규칙:
- 보이거나 들리는 행동만 적고, 발달 수준을 평가하거나 추측하지 않습니다.
- 몸의 움직임, 손의 사용, 물건을 다루는 방식, 말과 소리, 다른 사람과의 상호작용, 스스로 하는 일상 동작을 구체적으로 적습니다.
- 영상의 자막이나 글자는 근거로 쓰지 말고, 실제 행동만 봅니다.
- 얼굴 생김새, 옷, 이름, 장소처럼 아이를 식별할 수 있는 내용은 적지 않습니다.
- 발달 영역의 이름을 쓰지 않습니다."""

ITEM_GUIDE = """
아래는 관찰할 만한 행동 목록입니다. 영상과 관련된 행동이 있으면 더 자세히 살펴보세요.
목록에 없는 행동도 적고, 영상에 없는 행동은 적지 마세요. 목록의 문장을 그대로 옮기지 마세요.

{items}"""


def load_item_pool() -> list[KdstItem]:
    """모든 검사지의 문항을 모은다. 월령이 겹쳐 반복되는 문항은 하나만 남긴다."""
    seen: dict[str, KdstItem] = {}
    paths = sorted(config.KDST_DIR.glob("*.json"))
    for path in paths:
        if path.stem == "example":
            continue
        for row in json.loads(path.read_text(encoding="utf-8")):
            item = KdstItem(**row)
            seen.setdefault(re.sub(r"\s", "", item.text), item)
    return sorted(seen.values(), key=lambda item: (item.domain, item.text))


def build_prompt(mode: CaptionMode, items: list[KdstItem], age_months: int | None, single: bool = False) -> str:
    age = f"월령: 생후 {age_months}개월\n\n" if age_months is not None else ""
    guide = ""
    if mode == "item_conditioned":
        # 영역 이름을 숨기고 섞인 순서로 넣는다. 캡션에 영역 정보가 새지 않게 하기 위해서다.
        ordered = sorted(items, key=lambda item: hashlib.md5(item.text.encode()).hexdigest())
        guide = ITEM_GUIDE.format(items="\n".join(f"- {item.text}" for item in ordered))
    return age + (SINGLE_HEAD if single else BATCH_HEAD) + "\n" + RULES + guide


def load_videos() -> pd.DataFrame:
    """labels.csv에서 내용이 중복된 영상을 뺀 목록을 읽는다."""
    table = pd.read_csv(config.LABELS_CSV, dtype=str, keep_default_na=False)
    return table[table["duplicate_of"] == ""].reset_index(drop=True)


def first_per_domain(videos: pd.DataFrame, count: int) -> pd.DataFrame:
    """영역별 앞쪽 영상을 고른다. 두 캡션 모드를 같은 영상으로 비교하기 위해 쓴다."""
    return videos.sort_values("video_id").groupby("domain", sort=False).head(count)


def video_path(relative: str) -> Path:
    """CSV의 NFC 경로를 실제 파일로 찾는다. macOS 파일명은 NFD일 수 있다."""
    root = config.video_dir()
    folder, name = relative.split("/")
    for directory in root.iterdir():
        if unicodedata.normalize("NFC", directory.name) == folder:
            for path in directory.iterdir():
                if unicodedata.normalize("NFC", path.name) == name:
                    return path
    raise FileNotFoundError(relative)


def caption_batch(rows: list[dict], mode: CaptionMode, items: list[KdstItem]) -> dict[str, str]:
    """영상 여러 개를 한 번에 캡셔닝해 {video_id: 캡션}을 돌려준다."""
    numbers = list(range(1, len(rows) + 1))

    def check(result: CaptionBatch) -> None:
        returned = sorted(caption.video_number for caption in result.captions)
        if returned != numbers:
            raise ValueError(f"영상 번호가 맞지 않습니다: {returned}")
        if any(not caption.caption_text.strip() for caption in result.captions):
            raise ValueError("빈 캡션이 있습니다")

    prompt = build_prompt(mode, items, None)
    result = llm.generate(
        prompt,
        schema=CaptionBatch,
        videos=[video_path(row["file"]) for row in rows],
        check=check,
        tag=f"caption:{mode}:batch{len(rows)}",
    )
    return {rows[c.video_number - 1]["video_id"]: c.caption_text for c in result.captions}


def caption_single(row: dict, mode: CaptionMode, items: list[KdstItem]) -> str:
    """영상 1개 캡셔닝. 앞의 18개와 같은 프롬프트·스키마를 쓴다."""
    result = llm.generate(
        build_prompt(mode, items, None, single=True),
        schema=Caption,
        videos=[video_path(row["file"])],
        tag=f"caption:{mode}",
    )
    return result.caption_text


# ---------------------------------------------------------------- 호출 계획
PLAN_PATH = config.RESULTS_DIR / "caption_plan.json"
PLAN_SEED = 42


def build_plan(single_ids: list[str], videos: pd.DataFrame, batch_size: int = 5, per_domain: int = 5) -> dict:
    """영상별 호출 단위(단독/묶음)를 한 번 정해 고정한다.

    single_ids: 이미 1개씩 호출한 영상(차단 포함). 실험 ⑤ generic 표본은 영역별 5개다.
    단독 호출한 영역은 그 영상 중에서 고르고 generic도 단독 호출한다. 나머지 영역은
    묶음 영상에서 고르고, 그 영상들끼리만 묶어 두 모드의 묶음 구성이 같게 한다.
    """
    import random

    rng = random.Random(PLAN_SEED)
    rows = videos.sort_values("video_id")
    domain_of = dict(zip(rows["video_id"], rows["domain"]))
    single_set = set(single_ids)
    generic: set[str] = set()
    for domain, group in rows.groupby("domain", sort=False):
        ids = list(group["video_id"])
        singles = [v for v in ids if v in single_set]
        pool = singles if len(singles) >= per_domain else [v for v in ids if v not in single_set]
        generic.update(pool[:per_domain])

    units = [{"unit_id": f"S{i:02d}", "call": "single", "videos": [v], "generic": v in generic}
             for i, v in enumerate(sorted(single_set), 1)]
    rest = [v for v in rows["video_id"] if v not in single_set]
    shared = [v for v in rest if v in generic]
    others = [v for v in rest if v not in generic]
    rng.shuffle(shared)
    rng.shuffle(others)
    chunks = [(c, True) for c in _chunks(shared, batch_size)] + [(c, False) for c in _chunks(others, batch_size)]
    for i, (chunk, is_generic) in enumerate(chunks, 1):
        units.append({"unit_id": f"B{i:02d}", "call": "batch", "videos": chunk, "generic": is_generic})
    return {"seed": PLAN_SEED, "batch_size": batch_size, "per_domain": per_domain,
            "domains": {u["unit_id"]: [domain_of[v] for v in u["videos"]] for u in units},
            "units": units}


def _chunks(values: list, size: int) -> list[list]:
    return [values[i : i + size] for i in range(0, len(values), size)]


def load_plan() -> dict:
    return json.loads(PLAN_PATH.read_text(encoding="utf-8"))


def unit_of(plan: dict) -> dict[str, dict]:
    return {v: unit for unit in plan["units"] for v in unit["videos"]}
