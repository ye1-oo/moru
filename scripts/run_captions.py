"""영상 캡션을 일괄로 만든다. 캐시가 있어 끊겨도 다시 실행하면 이어서 진행된다.

예: python scripts/run_captions.py --mode item_conditioned --limit 1
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from moru import caption, config, llm  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=["item_conditioned", "generic"], default="item_conditioned")
    parser.add_argument("--video", help="video_id 하나만 처리")
    parser.add_argument("--limit", type=int)
    args = parser.parse_args()

    videos = caption.load_videos()
    if args.video:
        videos = videos[videos["video_id"] == args.video]
    if args.limit:
        videos = videos.head(args.limit)
    items = caption.load_item_pool()

    out = config.RESULTS_DIR / "raw" / f"captions_{config.GEMINI_MODEL}_{args.mode}.jsonl"
    out.parent.mkdir(parents=True, exist_ok=True)
    done = {}
    if out.exists():
        for line in out.read_text(encoding="utf-8").splitlines():
            row = json.loads(line)
            done[row["video_id"]] = row

    print(f"영상 {len(videos)}개, 문항 풀 {len(items)}개, 오늘 사용 {llm.calls_today()}회")
    try:
        for row in videos.to_dict("records"):
            if row["video_id"] in done:
                continue
            text = caption.caption_video(row, args.mode, items)
            done[row["video_id"]] = {
                "video_id": row["video_id"], "domain": row["domain"], "mode": args.mode,
                "model": config.GEMINI_MODEL, "caption": text,
            }
            with out.open("a", encoding="utf-8") as file:
                file.write(json.dumps(done[row["video_id"]], ensure_ascii=False) + "\n")
            print(f"  {row['video_id']} 완료 ({len(done)}개)", flush=True)
    except (llm.DailyQuotaExceeded, llm.ServerBusy) as error:
        print(f"중단, 나중에 다시 실행하면 이어서 진행됩니다: {error}")
    print(f"저장: {out} ({len(done)}개)")


if __name__ == "__main__":
    main()
