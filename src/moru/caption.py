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
from moru.schemas import Caption, CaptionMode, KdstItem

RULES = """당신은 영유아 영상을 객관적으로 기록하는 관찰자입니다.
영상에서 아이가 실제로 한 행동을 한국어 문장 3~6개로 묘사하세요.

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


def build_prompt(mode: CaptionMode, items: list[KdstItem], age_months: int | None) -> str:
    age = f"월령: 생후 {age_months}개월\n\n" if age_months is not None else ""
    guide = ""
    if mode == "item_conditioned":
        # 영역 이름을 숨기고 섞인 순서로 넣는다. 캡션에 영역 정보가 새지 않게 하기 위해서다.
        ordered = sorted(items, key=lambda item: hashlib.md5(item.text.encode()).hexdigest())
        guide = ITEM_GUIDE.format(items="\n".join(f"- {item.text}" for item in ordered))
    return age + RULES + guide


def load_videos() -> pd.DataFrame:
    """labels.csv에서 내용이 중복된 영상을 뺀 목록을 읽는다."""
    table = pd.read_csv(config.LABELS_CSV, dtype=str, keep_default_na=False)
    return table[table["duplicate_of"] == ""].reset_index(drop=True)


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


def caption_video(row: dict, mode: CaptionMode, items: list[KdstItem]) -> str:
    age = int(row["approx_age_months"]) if row["approx_age_months"] else None
    prompt = build_prompt(mode, items, age)
    result = llm.generate(
        prompt, schema=Caption, video=video_path(row["file"]), tag=f"caption:{mode}"
    )
    return result.caption_text
