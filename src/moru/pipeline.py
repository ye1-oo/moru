"""역할 분리형 멀티 에이전트 파이프라인의 조율기.

캡션 에이전트(인덱싱 때 1회) → 검색 에이전트 → 채점 에이전트 → 집계 → 리포트 에이전트
→ (조건부) 체크리스트 에이전트, (조건부) 상담 요약 에이전트(인터페이스만).

조율 규칙은 고정된 if 문이다. 에이전트가 스스로 다음 행동을 고르지 않는다.
- '정보 부족' 영역이 하나라도 있으면 → 그 영역의 판단 보류 문항으로 체크리스트 에이전트 호출
- 0~1점 문항이 있는 영역이 2주 연속이면 → 상담 요약 에이전트 호출 대상으로 기록(구현 안 함)

비교 실험용 조건(CONDITIONS)도 여기서 정의한다.
"""

import json
from dataclasses import dataclass, field
from datetime import date as Date
from pathlib import Path

from moru import caption, config, context, index, report, retrieve, score
from moru.context import Toggles
from moru.schemas import Diary, ItemScore, KdstItem

CHILD = "child_A"
DIARY_FILE = config.DIARY_DIR / "child_A.jsonl"
AGE_BAND = "18-19"
WEEKS = {1: (Date(2026, 10, 19), Date(2026, 10, 25)), 2: (Date(2026, 10, 26), Date(2026, 11, 1))}
RAW = config.RESULTS_DIR / "raw" / "exp_b"
CONTEXTS = config.RESULTS_DIR / "contexts"


@dataclass(frozen=True)
class Condition:
    name: str
    label: str
    toggles: Toggles = field(default_factory=Toggles)
    content: index.Content = "both"
    retrieval: str = "per_item"
    single: bool = False


CONDITIONS = {c.name: c for c in [
    Condition("multi", "멀티 에이전트(전체 적용)"),
    Condition("single", "단일 에이전트", single=True),
    Condition("no_date", "날짜 태그 제거", Toggles(use_date_tags=False)),
    Condition("no_source", "출처 태그 제거", Toggles(use_source_tags=False)),
    Condition("no_abstain", "판단 보류 규칙 제거", Toggles(use_abstain_rule=False)),
    Condition("none", "전체 제거", Toggles(False, False, False)),
    Condition("forced", "판단 보류 불가(일반 LLM 채점)", Toggles(use_abstain_rule=False, allow_abstain=False)),
    Condition("parent_only", "일기만", content="parent"),
    Condition("caption_only", "캡션만", content="caption"),
    Condition("batched", "일괄 검색", retrieval="batched"),
]}


def load_items() -> list[KdstItem]:
    return [KdstItem(**row) for row in json.loads((config.KDST_DIR / f"{AGE_BAND}.json").read_text(encoding="utf-8"))]


def week_diaries(week: int) -> list[Diary]:
    start, end = WEEKS[week]
    return [d for d in index.load_diaries(DIARY_FILE) if start <= d.date <= end]


_qdrant = None


def qdrant():
    global _qdrant
    if _qdrant is None:
        _qdrant = index.client()
    return _qdrant


def ensure_index(content: str) -> str:
    """세 가지 내용(both/parent/caption)의 컬렉션을 만든다. 임베딩은 캐시된다."""
    name = index.collection_name("kure", content)
    if not qdrant().collection_exists(name):
        index.build(qdrant(), index.load_diaries(DIARY_FILE), index.load_captions(), "kure", content)
    return name


def raw_path(condition: str, week: int, repeat: int) -> Path:
    return RAW / f"{condition}_w{week}_r{repeat}.json"


def prepare(condition: Condition, week: int) -> dict:
    """LLM 호출 전까지(검색 + 컨텍스트 조립). 호출 없이 컨텍스트를 확인할 수 있다."""
    items = load_items()
    start, end = WEEKS[week]
    diaries = week_diaries(week)
    if condition.single:
        media = [v for d in diaries for v in d.media]
        numbers = {v: n for n, v in enumerate(media, 1)}
        prompt = context.single_agent_context(items, diaries, numbers, 18, str(start), str(end), condition.toggles)
        return {"items": items, "diaries": diaries, "prompt": prompt, "evidence": [],
                "videos": [caption.video_path(_video_file(v)) for v in media]}
    collection = ensure_index(condition.content)
    search = retrieve.per_item if condition.retrieval == "per_item" else retrieve.batched
    evidence = search(qdrant(), collection, items, CHILD, start, end)
    prompt = context.scoring_context(items, evidence, 18, str(start), str(end), condition.toggles)
    return {"items": items, "diaries": diaries, "prompt": prompt, "evidence": evidence, "videos": []}


def _video_file(video_id: str) -> str:
    rows = caption.load_videos()
    return rows.loc[rows["video_id"] == video_id, "file"].iloc[0]


def run_scoring(name: str, week: int, repeat: int = 0) -> dict:
    """한 조건·한 주·한 반복을 채점하고 원본 결과를 저장한다(LLM 1회, 캐시되면 0회)."""
    condition = CONDITIONS[name]
    path = raw_path(name, week, repeat)
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    prep = prepare(condition, week)
    context.save(prep["prompt"], CONTEXTS / f"{name}_w{week}.txt")
    if condition.single:
        scores = score.single_agent(prep["prompt"], prep["items"], prep["videos"], repeat)
    else:
        scores = score.scoring_agent(prep["prompt"], prep["items"], repeat, tag=f"score:{name}",
                                     forced=not condition.toggles.allow_abstain)
    captions = index.load_captions()
    result = {
        "condition": name, "label": condition.label, "week": week, "repeat": repeat,
        "model": config.GEMINI_MODEL, "prompt": prep["prompt"],
        "evidence": {e.item_id: [r.diary_id for r in e.records] for e in prep["evidence"]},
        "scores": [s.model_dump() | {"flags": score.flags(s, prep["diaries"], captions)} for s in scores],
    }
    RAW.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")
    return result


def run_week_report(week: int, repeat: int = 0) -> dict:
    """멀티 에이전트 기본 조건의 end-to-end: 채점 → 집계 → 리포트 → 조율 규칙."""
    items = load_items()
    start, end = WEEKS[week]
    scored = run_scoring("multi", week, repeat)
    scores = [ItemScore(**{k: v for k, v in s.items() if k != "flags"}) for s in scored["scores"]]
    domains = report.aggregate(items, scores)
    previous = None
    if week - 1 in WEEKS and raw_path("multi", week - 1, repeat).exists():
        prev = json.loads(raw_path("multi", week - 1, repeat).read_text(encoding="utf-8"))
        previous = report.aggregate(items, [ItemScore(**{k: v for k, v in s.items() if k != "flags"})
                                            for s in prev["scores"]])
    week_out = {"child_id": CHILD, "week": week, "start": str(start), "end": str(end), "age_months": 18,
                "domains": domains, "changes": report.changes(domains, previous), "handoffs": []}

    prompt = context.report_context(18, str(start), str(end), domains, week_out["changes"], report.highlights(scores))
    context.save(prompt, CONTEXTS / f"report_w{week}.txt")
    week_out["report"] = report.report_agent(prompt, repeat).model_dump()

    # 조율 규칙 1: 정보 부족 영역 → 체크리스트 에이전트
    insufficient = {d["domain"] for d in domains if d["status"] == "정보 부족"}
    if insufficient:
        by_id = {s.item_id: s for s in scores}
        targets = [i for i in items if i.domain in insufficient and by_id[i.item_id].score is None]
        prompt = context.checklist_context(18, targets)
        context.save(prompt, CONTEXTS / f"checklist_w{week}.txt")
        week_out["checklist"] = report.checklist_agent(prompt, sorted(insufficient), repeat).model_dump()
        week_out["handoffs"].append(f"체크리스트 에이전트 호출: 정보 부족 영역 {sorted(insufficient)}")

    # 조율 규칙 2: 0~1점 문항이 있는 영역이 2주 연속 → 상담 요약 에이전트(인터페이스만)
    if previous:
        prev = {d["domain"]: d for d in previous}
        lasting = [d["domain"] for d in domains if d["concern"] and prev.get(d["domain"], {}).get("concern")]
        for domain in lasting:
            week_out["handoffs"].append(f"상담 요약 에이전트 호출 대상(미구현): {domain} 2주 연속 관찰 필요")

    out = config.RESULTS_DIR / "raw" / "reports"
    out.mkdir(parents=True, exist_ok=True)
    (out / f"{CHILD}_w{week}_r{repeat}.json").write_text(json.dumps(week_out, ensure_ascii=False, indent=1), encoding="utf-8")
    (out / f"{CHILD}_w{week}_r{repeat}.md").write_text(report.to_markdown(week_out), encoding="utf-8")
    return week_out


def combined_path() -> Path:
    return config.RESULTS_DIR / "raw" / "reports" / f"{CHILD}_combined.json"


def _scores(name: str, week: int, repeat: int = 0) -> list[ItemScore]:
    data = json.loads(raw_path(name, week, repeat).read_text(encoding="utf-8"))
    return [ItemScore(**{k: v for k, v in s.items() if k != "flags"}) for s in data["scores"]]


def run_combined_report() -> dict:
    """보고서·데모용: 2주 기록을 합친 기간 리포트(LLM 2회: 리포트 + 체크리스트).

    새로 채점하지 않고 멀티 에이전트 1·2주차 채점(반복 0)을 합친다. 문항마다 가장 최근 주의
    점수를 쓰고, 그 주가 판단 보류면 이전 주 점수를 쓴다. 근거 날짜는 그대로 남는다.
    """
    items = load_items()
    first, second = _scores("multi", 1), _scores("multi", 2)
    by_first = {s.item_id: s for s in first}
    merged = [s if s.score is not None else by_first[s.item_id] for s in second]
    domains = report.aggregate(items, merged)
    start, end = WEEKS[1][0], WEEKS[2][1]
    out = {"child_id": CHILD, "combined": True, "start": str(start), "end": str(end), "age_months": 18,
           "domains": domains, "changes": report.changes(report.aggregate(items, second), report.aggregate(items, first)),
           "handoffs": [], "scores": [s.model_dump() for s in merged]}
    prompt = context.report_context(18, str(start), str(end), domains, out["changes"], report.highlights(merged, 10))
    context.save(prompt, CONTEXTS / "report_combined.txt")
    out["report"] = report.report_agent(prompt).model_dump()
    insufficient = sorted({d["domain"] for d in domains if d["status"] == "정보 부족"})
    if insufficient:
        by_id = {s.item_id: s for s in merged}
        targets = [i for i in items if i.domain in insufficient and by_id[i.item_id].score is None]
        prompt = context.checklist_context(18, targets)
        context.save(prompt, CONTEXTS / "checklist_combined.txt")
        out["checklist"] = report.checklist_agent(prompt, insufficient).model_dump()
        out["handoffs"].append(f"체크리스트 에이전트 호출: 정보 부족 영역 {insufficient}")
    lasting = [d["domain"] for d, p in zip(report.aggregate(items, second), report.aggregate(items, first))
               if d["concern"] and p["concern"]]
    out["handoffs"] += [f"상담 요약 에이전트 호출 대상(미구현): {d} 2주 연속 관찰 필요" for d in lasting]
    path = combined_path()
    path.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    path.with_suffix(".md").write_text(report.to_markdown(out), encoding="utf-8")
    return out


# ---------------------------------------------------------------- 채팅·상담 요약 데모(웹 데모용)
DEMO = config.RESULTS_DIR / "demo"
CHAT_QUESTIONS = [
    "요즘 걷는 건 어때?",
    "말이 느린 것 같은데 괜찮아?",
    "혼자 밥 먹는 건 잘하고 있어?",
    "배변 훈련은 어떻게 되고 있어?",  # 기록에 없는 질문
]


def chat_path(n: int) -> Path:
    return DEMO / f"chat_{n}.json"


def run_chat(n: int) -> dict:
    """2주 전체 기간으로 질문 하나에 답한다(LLM 1회)."""
    from moru.interfaces import ChatAgent

    start, end = WEEKS[1][0], WEEKS[2][1]
    agent = ChatAgent(qdrant(), ensure_index("both"), 18)
    question = CHAT_QUESTIONS[n]
    output, records, prompt = agent.answer(CHILD, question, start, end)
    result = {"question": question, "period": [str(start), str(end)], "retrieved": [r.model_dump() for r in records],
              "output": output.model_dump(), "model": config.GEMINI_MODEL}
    DEMO.mkdir(parents=True, exist_ok=True)
    chat_path(n).write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")
    context.save(prompt, config.RESULTS_DIR / "examples" / "contexts" / f"chat_{n}.txt")  # 문항 원문 없음
    return result


def counsel_path() -> Path:
    return DEMO / "counsel.json"


def run_counsel() -> dict:
    """2주 합산 결과에서 우려 영역을 골라 상담 요약을 만든다(LLM 1회).

    조율 규칙(0~1점 문항 영역이 2주 연속)에 걸린 영역이 있으면 그 영역, 없으면 합산 결과에서
    0~1점 문항이 있는 영역을 쓴다. 어느 쪽이었는지 결과에 남긴다.
    """
    from moru.interfaces import CounselSummaryAgent

    combined = json.loads(combined_path().read_text(encoding="utf-8"))
    lasting = [h.split(": ")[1].split()[0] for h in combined["handoffs"] if h.startswith("상담 요약")]
    concern = [d["domain"] for d in combined["domains"] if d["concern"]]
    domain, trigger = (lasting[0], "조율 규칙: 2주 연속 0~1점 문항") if lasting else (
        concern[0], "데모용 직접 호출: 2주 합산 결과에서 0~1점 문항이 있는 영역(2주 연속 조건은 충족하지 않음)")
    start, end = WEEKS[1][0], WEEKS[2][1]
    agent = CounselSummaryAgent(qdrant(), ensure_index("both"), 18)
    output, records, prompt = agent.summarize(CHILD, domain, load_items(), combined["scores"], start, end)
    result = {"domain": domain, "trigger": trigger, "period": [str(start), str(end)],
              "retrieved": [r.model_dump() for r in records], "output": output.model_dump(), "model": config.GEMINI_MODEL}
    DEMO.mkdir(parents=True, exist_ok=True)
    counsel_path().write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")
    context.save(context.mask_items(prompt, load_items()), config.RESULTS_DIR / "examples" / "contexts" / "counsel.txt")
    return result
