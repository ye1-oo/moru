"""실험 B 실행기와 "오늘 몫" 작업 큐.

예: python experiments/exp_b_weekly_report.py today          # 남은 한도 안에서 큐를 순서대로 실행
    python experiments/exp_b_weekly_report.py plan           # 큐와 진행 상황만 출력(호출 없음)
    python experiments/exp_b_weekly_report.py run multi 2 0  # 조건·주·반복 하나
    python experiments/exp_b_weekly_report.py dump           # 호출 없이 조건별 컨텍스트만 저장

큐는 우선순위 순서다. 이미 결과가 있는 작업은 건너뛰고(캐시), 한도에 닿으면 멈춘다.
다음 날 같은 명령을 다시 실행하면 이어서 진행된다.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from moru import config, context, llm, pipeline  # noqa: E402

# (작업 종류, 조건, 주, 반복). 우선순위: 기본 end-to-end > ① 단일 vs 멀티 > ② 요소별 제거 > ③ 일기/캡션 > ④ 검색 방식
ABLATIONS = ["no_date", "no_source", "no_abstain", "none"]
MODALITY = ["parent_only", "caption_only"]


def queue() -> list[tuple]:
    """우선순위 큐(2026-11-09 조정).
    기본 end-to-end > ① > ② > ③ > 판단 보류 불가(기준선) > 2주 합산 리포트 > 채팅·상담 데모 > 반복.
    반복 우선순위: 멀티, 단일, 날짜 태그 제거, 판단 보류 불가 > 전체 제거 > 출처 태그 제거, 판단 보류 규칙 제거.
    ④ 일괄 검색은 향후 실험 계획."""
    q = [("score", "multi", 1, 0), ("score", "multi", 2, 0), ("report", "multi", 1, 0), ("report", "multi", 2, 0)]
    q += [("score", "single", w, 0) for w in (1, 2)]
    q += [("score", c, w, 0) for c in ABLATIONS for w in (1, 2)]
    q += [("score", c, w, 0) for c in MODALITY for w in (1, 2)]
    q += [("score", "forced", w, 0) for w in (1, 2)]
    q += [("combined", "multi", 0, 0)]
    q += [("chat", "multi", n, 0) for n in range(len(pipeline.CHAT_QUESTIONS))] + [("counsel", "multi", 0, 0)]
    for group in (["multi", "single", "no_date", "forced"], ["none"], ["no_source", "no_abstain"]):
        for rep in (1, 2):
            q += [("score", c, w, rep) for c in group for w in (1, 2)]
    return q


def report_done(week: int, rep: int) -> bool:
    return (config.RESULTS_DIR / "raw" / "reports" / f"{pipeline.CHILD}_w{week}_r{rep}.json").exists()


BLOCKED = config.RESULTS_DIR / "raw" / "exp_b_blocked.jsonl"


def blocked() -> set[tuple]:
    """안전 필터에 막힌 작업. 재전송하지 않고 실험에서 제외한다(CLAUDE.md 9장)."""
    if not BLOCKED.exists():
        return set()
    import json

    return {tuple(json.loads(line)["task"]) for line in BLOCKED.read_text(encoding="utf-8").splitlines()}


def done(task: tuple) -> bool:
    if task in blocked():
        return True
    kind, cond, week, rep = task
    if kind == "combined":
        return pipeline.combined_path().exists()
    if kind == "chat":
        return pipeline.chat_path(week).exists()
    if kind == "counsel":
        return pipeline.counsel_path().exists()
    return report_done(week, rep) if kind == "report" else pipeline.raw_path(cond, week, rep).exists()


def calls_needed(task: tuple) -> int:
    kind = task[0]
    return 2 if kind in ("report", "combined") else 1  # 리포트 + (조건부) 체크리스트


def run(task: tuple) -> None:
    kind, cond, week, rep = task
    if kind == "report":
        pipeline.run_week_report(week, rep)
    elif kind == "combined":
        pipeline.run_combined_report()
    elif kind == "chat":
        pipeline.run_chat(week)
    elif kind == "counsel":
        pipeline.run_counsel()
    else:
        pipeline.run_scoring(cond, week, rep)


def today(reserve: int = 0) -> None:
    pending = [t for t in queue() if not done(t)]
    print(f"{config.GEMINI_MODEL}: 오늘 {llm.calls_today()}/{config.GEMINI_RPD}회 사용, 남은 작업 {len(pending)}개", flush=True)
    for task in pending:
        left = config.GEMINI_RPD - llm.calls_today() - reserve
        if left < calls_needed(task):
            print(f"오늘 한도 소진(남은 {left}회). 다음 작업: {task}", flush=True)
            break
        try:
            run(task)
            print(f"  완료 {task} (오늘 {llm.calls_today()}회)", flush=True)
        except llm.DailyQuotaExceeded as error:
            print(f"한도 초과로 중단: {str(error)[:150]}", flush=True)
            break
        except llm.ServerBusy as error:
            print(f"서버 혼잡으로 중단, 다시 실행하면 이어집니다: {str(error)[:150]}", flush=True)
            break
        except ValueError as error:
            print(f"  실패(형식 오류 재시도 초과), 건너뜀 {task}: {str(error)[:150]}", flush=True)
        except llm.ContentBlocked as error:
            import json

            BLOCKED.parent.mkdir(parents=True, exist_ok=True)
            with BLOCKED.open("a", encoding="utf-8") as file:
                file.write(json.dumps({"task": list(task), "message": str(error)[:300]}, ensure_ascii=False) + "\n")
            print(f"  안전 필터 차단, 재전송하지 않고 제외 {task}", flush=True)
    status()


def status() -> None:
    q = queue()
    print(f"진행: {sum(done(t) for t in q)}/{len(q)}")
    for t in q:
        print(("  [x] " if done(t) else "  [ ] ") + " ".join(map(str, t)))


def dump() -> None:
    """호출 없이 조건별 컨텍스트를 저장하고, 문항 원문을 가린 사본을 results/examples/에 둔다."""
    items = pipeline.load_items()
    for name, condition in pipeline.CONDITIONS.items():
        for week in (1, 2):
            prompt = pipeline.prepare(condition, week)["prompt"]
            context.save(prompt, pipeline.CONTEXTS / f"{name}_w{week}.txt")
            context.save(context.mask_items(prompt, items),
                         config.RESULTS_DIR / "examples" / "contexts" / f"{name}_w{week}.txt")
    print("저장:", pipeline.CONTEXTS, "/ 마스킹본:", config.RESULTS_DIR / "examples" / "contexts")


if __name__ == "__main__":
    command = sys.argv[1] if len(sys.argv) > 1 else "plan"
    if command == "today":
        today()
    elif command == "run":
        run(("score", sys.argv[2], int(sys.argv[3]), int(sys.argv[4])))
    elif command == "dump":
        dump()
    else:
        status()
