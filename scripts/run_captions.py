"""영상 캡션을 일괄로 만든다. 캐시가 있어 끊겨도 다시 실행하면 이어서 진행된다.

예: python scripts/run_captions.py --mode item_conditioned --until-done
    python scripts/run_captions.py --mode generic --per-domain 5 --until-done

--until-done은 일일 한도에 닿으면 다음 초기화(한국 시간 17:00)까지 기다렸다가 이어서 한다.
"""

import argparse
import json
import sys
import time
from pathlib import Path

from pydantic import ValidationError

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from moru import caption, config, llm  # noqa: E402

BUSY_WAIT_SECONDS = 1200
MAX_BLOCKED = 3  # 안전 필터 차단이 이만큼 쌓이면 멈추고 사람이 판단한다
BLOCKED_LOG = config.RESULTS_DIR / "raw" / "caption_blocked.jsonl"


class TooManyBlocked(RuntimeError):
    pass


def load_blocked() -> set[str]:
    """차단된 영상은 모드와 상관없이 다시 보내지 않는다."""
    if not BLOCKED_LOG.exists():
        return set()
    lines = BLOCKED_LOG.read_text(encoding="utf-8").splitlines()
    return {json.loads(line)["video_id"] for line in lines}


def select_videos(args):
    videos = caption.load_videos()
    if args.video:
        videos = videos[videos["video_id"] == args.video]
    if args.per_domain:
        videos = caption.first_per_domain(videos, args.per_domain)
    if args.limit:
        videos = videos.head(args.limit)
    return videos


def run_once(videos, items, mode, out, failed) -> None:
    done = {}
    if out.exists():
        for line in out.read_text(encoding="utf-8").splitlines():
            row = json.loads(line)
            done[row["video_id"]] = row

    for row in videos.to_dict("records"):
        video_id = row["video_id"]
        blocked = load_blocked()
        if video_id in done or video_id in failed or video_id in blocked:
            continue
        try:
            text = caption.caption_video(row, mode, items)
        except llm.ContentBlocked:
            record = {"video_id": video_id, "domain": row["domain"], "model": config.GEMINI_MODEL}
            with BLOCKED_LOG.open("a", encoding="utf-8") as file:
                file.write(json.dumps(record, ensure_ascii=False) + "\n")
            print(f"  {video_id} 안전 필터 차단, 제외 ({len(blocked) + 1}개째)", flush=True)
            if len(blocked) + 1 >= MAX_BLOCKED:
                raise TooManyBlocked(f"차단 {MAX_BLOCKED}개, 사람이 확인할 때까지 멈춥니다")
            continue
        except (ValidationError, RuntimeError) as error:
            if isinstance(error, (llm.DailyQuotaExceeded, llm.ServerBusy)):
                raise
            failed[video_id] = str(error)[:200]
            print(f"  {video_id} 실패, 건너뜀: {failed[video_id]}", flush=True)
            continue
        record = {
            "video_id": video_id, "domain": row["domain"], "mode": mode,
            "model": config.GEMINI_MODEL, "caption": text,
        }
        done[video_id] = record
        with out.open("a", encoding="utf-8") as file:
            file.write(json.dumps(record, ensure_ascii=False) + "\n")
        print(f"  {video_id} 완료 ({len(done)}개, 오늘 {llm.calls_today()}회)", flush=True)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=["item_conditioned", "generic"], default="item_conditioned")
    parser.add_argument("--video", help="video_id 하나만 처리")
    parser.add_argument("--limit", type=int)
    parser.add_argument("--per-domain", type=int, help="영역별 앞에서 N개만 처리")
    parser.add_argument("--until-done", action="store_true", help="한도에 닿으면 기다렸다가 이어서 한다")
    args = parser.parse_args()

    videos = select_videos(args)
    items = caption.load_item_pool()
    out = config.RESULTS_DIR / "raw" / f"captions_{config.GEMINI_MODEL}_{args.mode}.jsonl"
    out.parent.mkdir(parents=True, exist_ok=True)
    failed: dict[str, str] = {}
    print(f"{config.GEMINI_MODEL}, 영상 {len(videos)}개, 문항 풀 {len(items)}개", flush=True)

    while True:
        try:
            run_once(videos, items, args.mode, out, failed)
            break
        except TooManyBlocked as error:
            print(f"중단: {error}", flush=True)
            break
        except llm.DailyQuotaExceeded as error:
            if not args.until_done:
                print(f"일일 한도 도달: {error}")
                break
            wait = llm.seconds_until_reset()
            print(f"일일 한도 도달, {wait / 3600:.1f}시간 대기: {str(error)[:200]}", flush=True)
            time.sleep(wait)
        except llm.ServerBusy as error:
            if not args.until_done:
                print(f"서버 과부하로 중단: {error}")
                break
            print(f"서버 과부하, {BUSY_WAIT_SECONDS // 60}분 대기: {str(error)[:200]}", flush=True)
            time.sleep(BUSY_WAIT_SECONDS)

    print(f"끝: {out}, 실패 {len(failed)}개 {list(failed)}", flush=True)


if __name__ == "__main__":
    main()
