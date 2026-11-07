"""에이전트별 컨텍스트 조립 (명세 4.3). 이 프로젝트의 핵심이라 프레임워크 없이 코드로 드러낸다.

각 에이전트는 자기 역할에 필요한 정보만 받는다.
- 채점 에이전트: [시스템 규칙] [아이 정보] [평가 기간] [채점 기준] [영역별: 근거 기록 + 문항] [출력 형식]
- 단일 에이전트(비교 ①): 같은 규칙 + 한 주 일기 전체 + 영상 원본 + 48문항 전체(검색 없음)
- 리포트 에이전트: 영역 집계, 이전 주 대비 변화, 핵심 근거만(일기 원문 전체는 넣지 않음)
- 체크리스트 에이전트: 판단 보류 문항 + 월령만(검색 없음)

토글(비교 ②): use_date_tags, use_source_tags, use_abstain_rule.
아이 이름 등 판단에 불필요한 개인정보는 넣지 않는다(입력 데이터에도 없다).
"""

import re
from dataclasses import dataclass
from pathlib import Path

from moru.schemas import Diary, Evidence, KdstItem, Record

DOMAIN_KO = {"gross_motor": "대근육운동", "fine_motor": "소근육운동", "cognition": "인지",
             "language": "언어", "social": "사회성", "self_care": "자조"}


@dataclass(frozen=True)
class Toggles:
    use_date_tags: bool = True
    use_source_tags: bool = True
    use_abstain_rule: bool = True


ROLE = "당신은 영유아 발달 기록을 읽고 K-DST 문항별 참고 평가값을 매기는 채점 담당입니다."
RULE_BASE = """규칙:
- 아래 기록에 적힌 내용만 근거로 삼습니다. 일반적인 발달 지식으로 추측하지 않습니다.
- evidence_quote에는 근거 기록의 문장을 바꾸지 말고 그대로 옮깁니다.
- 이 결과는 공식 검사 결과나 진단이 아닌 참고 평가값입니다."""
RULE_DATE = "- evidence_date에는 근거 기록 머리말의 날짜를 적습니다. '어제', '지난주부터' 같은 표현도 그 기록의 날짜로 적습니다."
RULE_SOURCE = """- 기록은 [부모 일기](부모가 쓴 글)와 [미디어 캡셔닝 내용](AI가 영상을 보고 쓴 행동 묘사)으로 나뉩니다.
  source에는 근거 문장이 나온 쪽(parent 또는 caption)을 적습니다.
- 부모 서술과 영상 묘사가 다르면 영상에서 관찰된 행동을 더 무겁게 보고, 점수를 보수적으로 매기고 confidence를 낮춥니다."""
RULE_ABSTAIN = """- 문항과 직접 관련된 행동이 기록에 없으면 점수를 매기지 않습니다(판단 보류).
  이때 score, evidence_quote, evidence_date, source를 모두 null로 둡니다. 비슷한 주제(예: 책을 좋아함)만으로 점수를 주지 않습니다."""
CRITERIA = """채점 기준(문항당 0~3):
3 잘 할 수 있다 / 2 할 수 있는 편이다 / 1 하지 못하는 편이다 / 0 전혀 할 수 없다"""
OUTPUT = "출력: 아래 모든 문항에 대해 items 배열에 하나씩, item_id를 그대로 적어 JSON으로 답합니다."


def rules(t: Toggles) -> str:
    lines = [ROLE, "", RULE_BASE]
    if t.use_date_tags:
        lines.append(RULE_DATE)
    if t.use_source_tags:
        lines.append(RULE_SOURCE)
    if t.use_abstain_rule:
        lines.append(RULE_ABSTAIN)
    return "\n".join(lines)


def record_block(number: int, record: Record, t: Toggles) -> str:
    head = f"[기록 {number}]"
    if t.use_date_tags:
        head += f" {record.date} (생후 {record.age_months}개월)"
    parts = [head]
    if t.use_source_tags:
        if record.parent_text:
            parts.append(f"[부모 일기] {record.parent_text}")
        if record.caption_text:
            parts.append(f"[미디어 캡셔닝 내용] {record.caption_text}")
    else:
        parts.append(" ".join(x for x in (record.parent_text, record.caption_text) if x))
    return "\n".join(parts)


def header(age_months: int, start: str, end: str) -> str:
    return f"[아이 정보] 생후 {age_months}개월\n[평가 기간] {start} ~ {end}"


def scoring_context(items: list[KdstItem], evidence: list[Evidence], age_months: int,
                    start: str, end: str, t: Toggles) -> str:
    """채점 에이전트 컨텍스트. 영역마다 검색된 기록을 한 번씩만 싣고(중복 제거) 문항이 번호로 가리킨다."""
    by_id = {e.item_id: e for e in evidence}
    blocks = [rules(t), "", header(age_months, start, end), "", CRITERIA]
    for domain in dict.fromkeys(item.domain for item in items):
        group = [item for item in items if item.domain == domain]
        numbering: dict[str, int] = {}
        for item in group:
            for record in by_id[item.item_id].records:
                numbering.setdefault(record.diary_id, len(numbering) + 1)
        records = {r.diary_id: r for item in group for r in by_id[item.item_id].records}
        blocks.append(f"\n## 평가 영역: {DOMAIN_KO[domain]}")
        blocks.append("### 근거 기록")
        ordered = sorted(numbering, key=numbering.get)
        blocks.extend([record_block(numbering[d], records[d], t) for d in ordered] or ["(검색된 기록 없음)"])
        blocks.append("### 문항")
        for item in group:
            refs = ", ".join(f"기록 {numbering[r.diary_id]}" for r in by_id[item.item_id].records) or "없음"
            blocks.append(f"- {item.item_id}: {item.text} (검색된 기록: {refs})")
    blocks += ["", OUTPUT]
    return "\n".join(blocks)


def single_agent_context(items: list[KdstItem], diaries: list[Diary], video_numbers: dict[str, int],
                         age_months: int, start: str, end: str, t: Toggles) -> str:
    """단일 에이전트 컨텍스트: 검색·캡션 없이 한 주 일기 전체와 영상 원본, 48문항을 한 번에 넣는다."""
    blocks = [rules(t).replace("[미디어 캡셔닝 내용](AI가 영상을 보고 쓴 행동 묘사)", "[첨부 영상](앞에 붙은 영상 원본)")
              .replace("parent 또는 caption", "parent 또는 caption(영상이면 caption)"),
              "", header(age_months, start, end), "", CRITERIA, "", "## 이번 주 기록"]
    for n, diary in enumerate(diaries, 1):
        head = f"[기록 {n}]" + (f" {diary.date} (생후 {diary.age_months}개월)" if t.use_date_tags else "")
        lines = [head, (f"[부모 일기] " if t.use_source_tags else "") + diary.parent_text]
        if diary.media:
            lines.append("[첨부 영상] " + ", ".join(f"영상 {video_numbers[v]}" for v in diary.media))
        blocks.append("\n".join(lines))
    blocks.append("\n## 문항")
    blocks.append("영상 근거를 쓸 때 evidence_quote에는 영상에서 본 행동을 한 문장으로 적습니다.")
    for domain in dict.fromkeys(item.domain for item in items):
        blocks.append(f"### {DOMAIN_KO[domain]}")
        blocks.extend(f"- {item.item_id}: {item.text}" for item in items if item.domain == domain)
    blocks += ["", OUTPUT]
    return "\n".join(blocks)


REPORT_ROLE = """당신은 부모에게 이번 주 발달 관찰 결과를 설명하는 리포트 담당입니다.
규칙:
- 아래 집계와 핵심 근거만 사용합니다.
- 진단이나 공식 검사 결과처럼 말하지 않습니다. '참고 평가값'이라고 부릅니다.
- 한 주 결과만으로 발달이 늦다·빠르다고 단정하지 않습니다. 변화는 '이번 주 기록에서는'처럼 표현합니다.
- '정보 부족' 영역은 평가하지 말고 더 관찰해 보자고 안내합니다.
- 부모를 불안하게 하는 표현을 피하고, 필요하면 전문가 상담을 권할 수 있다고만 적습니다."""


def report_context(age_months: int, start: str, end: str, domains: list[dict],
                   changes: list[str], highlights: list[str]) -> str:
    lines = [REPORT_ROLE, "", header(age_months, start, end), "", "## 영역별 집계"]
    for d in domains:
        lines.append(f"- {DOMAIN_KO[d['domain']]}: 상태 {d['status']}, 참고 평가값 {d['total']}/{d['max_scored']} "
                     f"(채점 {d['scored']}문항, 판단 보류 {d['abstained']}문항)")
    lines += ["", "## 이전 주 대비 변화"] + ([f"- {c}" for c in changes] or ["- 이전 주 결과 없음"])
    lines += ["", "## 핵심 근거(날짜, 출처)"] + [f"- {h}" for h in highlights]
    lines += ["", "출력: summary(3~5문장)와 영역별 domain_notes를 JSON으로 답합니다."]
    return "\n".join(lines)


CHECKLIST_ROLE = """당신은 부모에게 다음 주에 관찰해 볼 행동을 제안하는 체크리스트 담당입니다.
아래 문항은 이번 주 기록에서 근거를 찾지 못한(판단 보류) 문항입니다.
문항마다 집에서 관찰할 행동 한 문장(observe)과 그 행동을 자연스럽게 볼 수 있는 놀이 한 문장(play)을 씁니다.
평가하거나 걱정을 주는 표현은 쓰지 않습니다."""


def checklist_context(age_months: int, items: list[KdstItem]) -> str:
    lines = [CHECKLIST_ROLE, "", f"[아이 정보] 생후 {age_months}개월", "", "## 판단 보류 문항"]
    for domain in dict.fromkeys(item.domain for item in items):
        lines.append(f"### {DOMAIN_KO[domain]}")
        lines.extend(f"- {item.item_id}: {item.text}" for item in items if item.domain == domain)
    lines += ["", "출력: entries 배열에 문항마다 하나씩 JSON으로 답합니다."]
    return "\n".join(lines)


def save(text: str, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def mask_items(text: str, items: list[KdstItem]) -> str:
    """저장소에 올릴 덤프에서 K-DST 문항 원문을 가린다(복제 금지 문구 때문)."""
    for item in sorted(items, key=lambda i: -len(i.text)):
        text = text.replace(item.text, f"〈문항 원문 비공개: {item.item_id}〉")
    return re.sub(r"\n{3,}", "\n\n", text)
