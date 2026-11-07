"""고정된 호출 계획(results/caption_plan.json)대로 영상 캡션을 만든다.

예: python scripts/run_captions.py --mode item_conditioned --max-units 1
    python scripts/run_captions.py --mode generic

계획에는 영상마다 호출 단위(단독 S##, 묶음 B##)가 정해져 있다. 무료 한도(모델별 하루 20회)
때문에 앞의 18개 이후는 5개씩 묶는다. 묶음은 고정 시드로 섞어 영역이 섞이게 만든다.
generic은 영역별 5개 표본만, item_conditioned와 같은 호출 단위로 보낸다.
끊겨도 다시 실행하면 남은 단위부터 이어서 진행된다.

안전 필터가 묶음을 막으면 원인 영상을 알 수 없으므로 재전송하지 않고 묶음 전체를 제외한다.
차단이 3번 쌓이면 멈춘다.
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from moru import caption, config, llm  # noqa: E402

MAX_BLOCKED = 3
RAW = config.RESULTS_DIR / "raw"
BLOCKED_LOG = RAW / "caption_blocked.jsonl"


def read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def append_jsonl(path: Path, record: dict) -> None:
    with path.open("a", encoding="utf-8") as file:
        file.write(json.dumps(record, ensure_ascii=False) + "\n")


def output_path(mode: str) -> Path:
    return RAW / f"captions_{config.GEMINI_MODEL}_{mode}.jsonl"


def ensure_plan() -> dict:
    """계획이 없으면 만든다. 이미 1개씩 호출한 영상(완료·차단)은 단독 단위로 남긴다."""
    if caption.PLAN_PATH.exists():
        return caption.load_plan()
    done = read_jsonl(output_path("item_conditioned")) + read_jsonl(BLOCKED_LOG)
    singles = [r["video_id"] for r in done if not r.get("batch")]
    plan = caption.build_plan(singles, caption.load_videos())
    caption.PLAN_PATH.write_text(json.dumps(plan, ensure_ascii=False, indent=1), encoding="utf-8")
    return plan


def pending_units(plan: dict, mode: str) -> list[dict]:
    blocked = {(r.get("mode", "item_conditioned"), r["video_id"]) for r in read_jsonl(BLOCKED_LOG)}
    done = {r["video_id"] for r in read_jsonl(output_path(mode))}
    units = [u for u in plan["units"] if mode == "item_conditioned" or u["generic"]]
    # 실험 A 중단(2026-11-07): 98개 전체 캡셔닝은 하지 않는다. 계획 밖 묶음(X##)만 실행한다.
    return [u for u in units
            if not any(v in done or (mode, v) in blocked for v in u["videos"])]


def blocked_events() -> int:
    return len({r.get("event", r["video_id"]) for r in read_jsonl(BLOCKED_LOG)})


def run(mode: str, max_units: int | None = None, only: str | None = None) -> int:
    """남은 단위를 실행하고 완료한 단위 수를 돌려준다. 한도에 닿으면 멈춘다."""
    plan = ensure_plan()
    rows = {r["video_id"]: r for r in caption.load_videos().to_dict("records")}
    items = caption.load_item_pool()
    units = [u for u in pending_units(plan, mode) if only is None or u["unit_id"] == only][:max_units]
    print(f"{config.GEMINI_MODEL} {mode}: 남은 단위 {len(pending_units(plan, mode))}개, "
          f"이번 {len(units)}개, 오늘 {llm.calls_today()}회 사용", flush=True)
    finished = 0
    try:
        for unit in units:
            batch = [rows[v] for v in unit["videos"]]
            try:
                if unit["call"] == "single":
                    captions = {batch[0]["video_id"]: caption.caption_single(batch[0], mode, items)}
                else:
                    captions = caption.caption_batch(batch, mode, items)
            except llm.ContentBlocked:
                for row in batch:
                    append_jsonl(BLOCKED_LOG, {
                        "video_id": row["video_id"], "domain": row["domain"], "mode": mode,
                        "model": config.GEMINI_MODEL, "call": unit["call"],
                        "unit_id": unit["unit_id"], "event": f"{mode}:{unit['unit_id']}",
                    })
                count = blocked_events()
                print(f"  {unit['unit_id']} 안전 필터 차단, 단위 전체 제외 ({count}번째)", flush=True)
                if count >= MAX_BLOCKED:
                    print("중단: 차단이 3번 쌓여 사람이 확인할 때까지 멈춥니다", flush=True)
                    break
                continue
            except ValueError as error:
                print(f"  {unit['unit_id']} 실패, 건너뜀: {str(error)[:200]}", flush=True)
                continue
            for row in batch:
                append_jsonl(output_path(mode), {
                    "video_id": row["video_id"], "domain": row["domain"], "mode": mode,
                    "model": config.GEMINI_MODEL, "call": unit["call"], "unit_id": unit["unit_id"],
                    "batch": unit["videos"], "caption": captions[row["video_id"]],
                })
            finished += 1
            print(f"  {unit['unit_id']} {unit['videos']} 완료 (오늘 {llm.calls_today()}회)", flush=True)
    except (llm.DailyQuotaExceeded, llm.ServerBusy) as error:
        print(f"중단, 다시 실행하면 이어서 진행됩니다: {str(error)[:200]}", flush=True)
    total = len(read_jsonl(output_path(mode)))
    print(f"끝: 이번 {finished}개 단위 완료, {mode} 캡션 전체 {total}개", flush=True)
    return finished


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=["item_conditioned", "generic"], default="item_conditioned")
    parser.add_argument("--max-units", type=int, help="이번 실행에서 보낼 호출 단위 수")
    parser.add_argument("--plan-only", action="store_true", help="계획만 만들고 출력")
    parser.add_argument("--extra", help="계획 밖의 영상 묶음(쉼표 구분). 실험 B 일기 첨부용")
    parser.add_argument("--unit-id", default="X01")
    args = parser.parse_args()
    if args.extra:
        plan = ensure_plan()
        ids = args.extra.split(",")
        if not any(u["unit_id"] == args.unit_id for u in plan["units"]):
            plan["units"].append({"unit_id": args.unit_id, "call": "batch" if len(ids) > 1 else "single",
                                  "videos": ids, "generic": False, "purpose": "exp_b_diary"})
            caption.PLAN_PATH.write_text(json.dumps(plan, ensure_ascii=False, indent=1), encoding="utf-8")
        args.only = args.unit_id
    if args.plan_only:
        plan = ensure_plan()
        for unit in plan["units"]:
            print(unit["unit_id"], unit["call"], "generic" if unit["generic"] else "", plan["domains"][unit["unit_id"]])
        return
    run(args.mode, args.max_units, getattr(args, "only", None))


if __name__ == "__main__":
    main()
