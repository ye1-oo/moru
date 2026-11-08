"""집계, 주차 비교, 리포트 에이전트, 체크리스트 에이전트 (명세 4.5, 4.6)."""

from moru import config, llm
from moru.context import DOMAIN_KO
from moru.schemas import ChecklistOutput, ItemScore, KdstItem, ReportOutput

CONCERN_MAX_SCORE = 1  # 영역에 0~1점 문항이 있으면 '관찰 필요' 영역으로 본다


def aggregate(items: list[KdstItem], scores: list[ItemScore]) -> list[dict]:
    """영역 합계와 상태. 판단 보류 비율이 ABSTAIN_DOMAIN_RATIO 이상이면 '정보 부족'."""
    by_id = {s.item_id: s for s in scores}
    out = []
    for domain in dict.fromkeys(i.domain for i in items):
        group = [by_id[i.item_id] for i in items if i.domain == domain]
        scored = [s for s in group if s.score is not None]
        abstained = len(group) - len(scored)
        insufficient = abstained / len(group) >= config.ABSTAIN_DOMAIN_RATIO
        out.append({
            "domain": domain, "items": len(group), "scored": len(scored), "abstained": abstained,
            "total": sum(s.score for s in scored), "max_scored": 3 * len(scored), "max": 3 * len(group),
            "status": "정보 부족" if insufficient else "평가",
            "concern": any(s.score <= CONCERN_MAX_SCORE for s in scored),
            "low_items": [s.item_id for s in scored if s.score <= CONCERN_MAX_SCORE],
        })
    return out


def changes(current: list[dict], previous: list[dict] | None) -> list[str]:
    if not previous:
        return []
    prev = {d["domain"]: d for d in previous}
    lines = []
    for d in current:
        p = prev.get(d["domain"])
        if not p:
            continue
        name = DOMAIN_KO[d["domain"]]
        if p["status"] != d["status"]:
            lines.append(f"{name}: 상태 {p['status']} → {d['status']}")
        elif d["status"] == "평가" and p["scored"] and d["scored"]:
            before, after = p["total"] / p["scored"], d["total"] / d["scored"]
            if abs(after - before) >= 0.5:
                lines.append(f"{name}: 채점 문항 평균 {before:.1f} → {after:.1f}")
        if p["concern"] and d["concern"]:
            lines.append(f"{name}: 0~1점 문항이 2주 연속 있음")
    return lines


def highlights(scores: list[ItemScore], limit: int = 8) -> list[str]:
    scored = sorted((s for s in scores if s.score is not None), key=lambda s: -s.confidence)[:limit]
    return [f"{s.evidence_date} ({s.source}) {s.item_id} {s.score}점: {s.evidence_quote}" for s in scored]


def report_agent(prompt: str, repeat: int = 0) -> ReportOutput:
    return llm.generate(prompt, schema=ReportOutput, repeat=repeat, tag="report")


def checklist_agent(prompt: str, domains: list[str], repeat: int = 0) -> ChecklistOutput:
    def check(result: ChecklistOutput) -> None:
        if sorted(d.domain for d in result.domains) != sorted(domains):
            raise ValueError("체크리스트 영역이 맞지 않습니다")
        if any(not 2 <= len(d.behaviors) <= 3 for d in result.domains):
            raise ValueError("영역마다 행동 2~3개가 필요합니다")
    return llm.generate(prompt, schema=ChecklistOutput, check=check, repeat=repeat, tag="checklist")


def to_markdown(week: dict) -> str:
    title = "기간 리포트" if week.get("combined") else "주간 리포트"
    lines = [f"# MORU {title} ({week['start']} ~ {week['end']}, 생후 {week['age_months']}개월)", "",
             "> 참고 평가값이며 공식 K-DST 결과나 진단이 아닙니다.", "", "## 영역별 참고 평가값", "",
             "| 영역 | 상태 | 참고 평가값 | 채점/보류 |", "|---|---|---|---|"]
    for d in week["domains"]:
        value = f"{d['total']}/{d['max_scored']}" if d["status"] == "평가" else "-"
        lines.append(f"| {DOMAIN_KO[d['domain']]} | {d['status']} | {value} | {d['scored']}/{d['abstained']} |")
    heading = "기간 안의 주간 변화(1주차 → 2주차)" if week.get("combined") else "이전 주 대비 변화"
    lines += ["", f"## {heading}", ""] + ([f"- {c}" for c in week["changes"]] or ["- 변화 없음 또는 이전 주 결과 없음"])
    if week.get("report"):
        lines += ["", "## 종합 소견", "", week["report"]["summary"], ""]
        lines += [f"- **{DOMAIN_KO[n['domain']]}**: {n['note']}" for n in week["report"]["domain_notes"]]
    if week.get("checklist"):
        lines += ["", "## 다음 주 관찰 체크리스트", ""]
        if "domains" in week["checklist"]:
            for d in week["checklist"]["domains"]:
                lines += [f"**{DOMAIN_KO[d['domain']]}**"]
                lines += [f"- [ ] {b['observe']} — 놀이: {b['play']}" for b in d["behaviors"]]
        else:  # 2026-11-07 형식(문항별)
            lines += [f"- [ ] ({e['item_id']}) {e['observe']} — 놀이: {e['play']}" for e in week["checklist"]["entries"]]
    if week.get("handoffs"):
        lines += ["", "## 조율 기록", ""] + [f"- {h}" for h in week["handoffs"]]
    return "\n".join(lines) + "\n"
