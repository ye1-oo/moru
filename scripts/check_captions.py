"""캡션에 아이 이름이나 영상 자막이 들어갔는지 검사한다.

이름 목록이 없으므로 의심 문장을 넓게 찾아 사람이 확인한다. 결과에는 캡션 원문이
들어가므로 커밋되지 않는 results/raw/caption_review.csv에 저장한다.
"""

import json
import re
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from moru import config  # noqa: E402

OVERLAY = re.compile(r"자막|글자|글씨|문구|텍스트|화면에|DAY|Day|이름|유튜브|채널|구독")
QUOTED = re.compile(r"[\"“‘'][^\"”’']{1,30}[\"”’']")
# "OO이가", "OO는" 처럼 호칭으로 쓰인 짧은 단어. 일반 명사는 아래에서 뺀다.
NAME_LIKE = re.compile(r"(?<![가-힣])([가-힣]{2,3}이)(?:가|는|를|의|도|와|에게)(?![가-힣])")
COMMON = {"아이", "어린이", "손가락이", "장난감이", "어른이", "아기이"}


def find_flags(text: str) -> list[str]:
    flags = [f"자막:{m}" for m in OVERLAY.findall(text)]
    flags += [f"따옴표:{m}" for m in QUOTED.findall(text)]
    flags += [f"이름?:{m}" for m in NAME_LIKE.findall(text) if m not in COMMON]
    return flags


def main() -> None:
    rows = []
    paths = sorted((config.RESULTS_DIR / "raw").glob("captions_*.jsonl"))
    total = 0
    for path in paths:
        for line in path.read_text(encoding="utf-8").splitlines():
            record = json.loads(line)
            total += 1
            flags = find_flags(record["caption"])
            if flags:
                rows.append(
                    {"file": path.name, "video_id": record["video_id"],
                     "flags": " | ".join(flags), "caption": record["caption"]}
                )
    out = config.RESULTS_DIR / "raw" / "caption_review.csv"
    pd.DataFrame(rows).to_csv(out, index=False)
    print(f"캡션 {total}개 중 확인 필요 {len(rows)}개: {out}")


if __name__ == "__main__":
    main()
