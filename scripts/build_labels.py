"""영상 폴더를 읽어 data/videos/labels.csv를 만든다.

폴더 이름이 영역 라벨이다. 다시 실행해도 직접 채운 선택 열은 유지된다.
macOS 파일명은 NFD일 수 있으므로 CSV에는 NFC로 저장하고, 내용이 똑같은
영상은 duplicate_of 열에 표시만 한다(제외 여부는 실험 코드가 정한다).
"""

import hashlib
import sys
import unicodedata
from collections import Counter
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from moru.config import DOMAIN_SLUGS, LABELS_CSV, video_dir  # noqa: E402

VIDEO_EXTS = {".mp4", ".mov"}
USER_COLUMNS = ["gold_behavior", "approx_age_months", "item_ids"]


def nfc(text: str) -> str:
    return unicodedata.normalize("NFC", text)


def md5(path: Path) -> str:
    return hashlib.md5(path.read_bytes()).hexdigest()


def scan(root: Path) -> pd.DataFrame:
    rows = []
    seen: dict[str, str] = {}
    folders = {nfc(p.name): p for p in root.iterdir() if p.is_dir()}
    unknown = set(folders) - set(DOMAIN_SLUGS)
    if unknown:
        raise ValueError(f"영역 매핑에 없는 폴더: {sorted(unknown)}")

    for korean, slug in DOMAIN_SLUGS.items():
        if korean not in folders:
            raise ValueError(f"영역 폴더가 없습니다: {korean}")
        files = [p for p in folders[korean].iterdir() if p.suffix.lower() in VIDEO_EXTS]
        for path in sorted(files, key=lambda p: nfc(p.name)):
            stem = nfc(path.stem).removeprefix(f"{korean}_").strip()
            video_id = f"{slug}_{stem}"
            digest = md5(path)
            rows.append(
                {
                    "video_id": video_id,
                    "file": f"{korean}/{nfc(path.name)}",
                    "domain": slug,
                    "duplicate_of": seen.get(digest, ""),
                }
            )
            seen.setdefault(digest, video_id)

    table = pd.DataFrame(rows)
    repeated = table["video_id"][table["video_id"].duplicated()].tolist()
    if repeated:
        raise ValueError(f"video_id가 겹칩니다: {repeated}")
    return table


def keep_user_columns(table: pd.DataFrame, path: Path) -> pd.DataFrame:
    if path.exists():
        old = pd.read_csv(path, dtype=str, keep_default_na=False)
        table = table.merge(old[["video_id", *USER_COLUMNS]], on="video_id", how="left")
    for column in USER_COLUMNS:
        table[column] = table[column].fillna("") if column in table else ""
    return table


def main() -> None:
    table = keep_user_columns(scan(video_dir()), LABELS_CSV)
    LABELS_CSV.parent.mkdir(parents=True, exist_ok=True)
    table.to_csv(LABELS_CSV, index=False)

    print(f"{LABELS_CSV} 저장: {len(table)}개")
    for domain, count in Counter(table["domain"]).items():
        print(f"  {domain}: {count}")
    for row in table[table["duplicate_of"] != ""].itertuples():
        print(f"  중복: {row.video_id} = {row.duplicate_of}")


if __name__ == "__main__":
    main()
