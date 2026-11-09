"""채팅 에이전트와 상담 요약 에이전트 (2026-11-09 인터페이스 → 동작하는 코드).

두 에이전트 모두 채점과 같은 검색 모듈(retrieve.search)을 재사용한다. 새 검색 로직은 없다.
- 채팅: 부모 질문 → 기간 안 기록 검색(top-k) → 기록에 있는 내용만, 날짜를 밝혀 답한다.
  관련 기록이 없으면 "기록에 없다"고 답한다(채점의 판단 보류와 같은 원칙).
- 상담 요약: 우려 영역의 낮은 점수 문항으로 기록을 검색 → 상담사가 읽을 요약.
  파이프라인 조율 규칙(0~1점 문항 영역이 2주 연속)이 호출 대상을 정한다. 데모에서는 직접 호출할 수 있다.
상담사 연결(예약, 전송)은 구현하지 않는다.
"""

from pydantic import BaseModel, Field

from moru import llm, retrieve
from moru.context import DOMAIN_KO
from moru.schemas import Domain, KdstItem, Record, Source


class Citation(BaseModel):
    date: str = Field(description="근거 기록의 날짜 YYYY-MM-DD")
    source: Source = Field(description="parent 또는 caption")
    quote: str = Field(description="근거 기록의 문장을 그대로")


class ChatOutput(BaseModel):
    answer: str = Field(description="부모에게 하는 답변 2~4문장. 근거 날짜를 문장 안에 밝힌다")
    has_evidence: bool = Field(description="질문과 직접 관련된 기록이 있었는가")
    citations: list[Citation] = Field(description="답변에 쓴 근거. 없으면 빈 배열")


class CounselOutput(BaseModel):
    domain: Domain
    summary: str = Field(description="상담사가 읽을 3~5문장 요약. 관찰 사실과 날짜 중심, 진단하지 않음")
    observations: list[Citation] = Field(description="요약의 근거가 된 기록")
    open_questions: list[str] = Field(description="상담에서 확인해 볼 점 2~3개")
    limitations: str = Field(description="이 요약의 한계 한두 문장(기록 수, 부모 서술과 AI 캡션의 차이 등)")


def records_block(records: list[Record]) -> str:
    """채점 에이전트와 같은 형식(날짜 태그 + 출처 태그)으로 기록을 싣는다."""
    blocks = []
    for n, r in enumerate(sorted(records, key=lambda r: r.date), 1):
        lines = [f"[기록 {n}] {r.date} (생후 {r.age_months}개월)"]
        if r.parent_text:
            lines.append(f"[부모 일기] {r.parent_text}")
        if r.caption_text:
            lines.append(f"[미디어 캡셔닝 내용] {r.caption_text}")
        blocks.append("\n".join(lines))
    return "\n".join(blocks) or "(검색된 기록 없음)"


CHAT_ROLE = """당신은 부모의 질문에 아이의 육아 기록만을 근거로 답하는 상담 도우미입니다.
규칙:
- 아래 검색된 기록에 적힌 내용만 근거로 답합니다. 일반적인 발달 지식으로 아이를 평가하지 않습니다.
- 근거를 쓸 때는 날짜를 밝힙니다(예: "10월 27일 기록에서는 ...").
- [부모 일기]와 [미디어 캡셔닝 내용](AI가 영상을 보고 쓴 묘사)을 구분해 말합니다.
- 질문과 직접 관련된 기록이 없으면 "이번 기간 기록에는 관련 내용이 없다"고 답하고, has_evidence를 false로, citations를 빈 배열로 둡니다. 관찰해 볼 방법을 한 문장 제안할 수 있습니다.
- 진단하거나 발달이 늦다·빠르다고 단정하지 않습니다. 걱정이 계속되면 전문가 상담을 권할 수 있습니다."""


def chat_context(question: str, age_months: int, start: str, end: str, records: list[Record]) -> str:
    return "\n".join([CHAT_ROLE, "", f"[아이 정보] 생후 {age_months}개월", f"[기록 기간] {start} ~ {end}", "",
                      "## 검색된 기록", records_block(records), "", f"## 부모 질문\n{question}", "",
                      "출력: answer, has_evidence, citations를 JSON으로 답합니다."])


class ChatAgent:
    """부모 질문 → retrieve.search() → 기록 근거 답변."""

    def __init__(self, qdrant, collection: str, age_months: int, k: int = 3):
        self.qdrant, self.collection, self.age_months, self.k = qdrant, collection, age_months, k

    def answer(self, child_id: str, question: str, start, end) -> tuple[ChatOutput, list[Record], str]:
        records = retrieve.search(self.qdrant, self.collection, question, child_id, start, end, self.k)
        prompt = chat_context(question, self.age_months, str(start), str(end), records)
        return llm.generate(prompt, schema=ChatOutput, tag="chat"), records, prompt


COUNSEL_ROLE = """당신은 발달 상담사에게 넘길 관찰 요약을 쓰는 담당입니다.
규칙:
- 아래 참고 평가값과 검색된 기록에 적힌 내용만 씁니다. 진단하거나 원인을 추정하지 않습니다.
- 관찰 사실을 날짜와 함께 적고, 부모 서술과 AI 영상 묘사를 구분합니다.
- 검사 문항의 문장을 그대로 옮기지 않습니다.
- 점수는 공식 검사 결과가 아닌 참고 평가값이라고 적습니다."""


def counsel_context(domain: str, age_months: int, start: str, end: str, domain_rows: list[str],
                    records: list[Record]) -> str:
    return "\n".join([COUNSEL_ROLE, "", f"[아이 정보] 생후 {age_months}개월", f"[기록 기간] {start} ~ {end}",
                      f"[우려 영역] {DOMAIN_KO[domain]} ({domain})", "", "## 이 영역의 참고 평가값(문항 번호, 점수, 근거 날짜)",
                      *domain_rows, "", "## 검색된 기록", records_block(records), "",
                      "출력: domain, summary, observations, open_questions, limitations를 JSON으로 답합니다."])


class CounselSummaryAgent:
    """우려 영역 → 낮은 점수 문항으로 retrieve.search() → 상담사용 요약."""

    def __init__(self, qdrant, collection: str, age_months: int, k: int = 3):
        self.qdrant, self.collection, self.age_months, self.k = qdrant, collection, age_months, k

    def summarize(self, child_id: str, domain: str, items: list[KdstItem], scores: list[dict],
                  start, end) -> tuple[CounselOutput, list[Record], str]:
        group = [i for i in items if i.domain == domain]
        by_id = {s["item_id"]: s for s in scores}
        low = [i for i in group if by_id[i.item_id]["score"] is not None and by_id[i.item_id]["score"] <= 1] or group
        found: dict[str, Record] = {}
        for item in low:
            for r in retrieve.search(self.qdrant, self.collection, item.text, child_id, start, end, self.k):
                found.setdefault(r.diary_id, r)
        rows = [f"- {i.item_id}: " + ("판단 보류" if by_id[i.item_id]["score"] is None else
                f"{by_id[i.item_id]['score']}점 ({by_id[i.item_id]['evidence_date']})") for i in group]
        prompt = counsel_context(domain, self.age_months, str(start), str(end), rows, list(found.values()))
        return llm.generate(prompt, schema=CounselOutput, tag="counsel"), list(found.values()), prompt
