"""기획만 하고 구현하지 않은 에이전트의 인터페이스.

채팅 에이전트와 상담 요약 에이전트는 retrieve.search()를 그대로 재사용하도록 설계했다.
구현은 이번 범위가 아니므로 호출하면 NotImplementedError를 낸다.
파이프라인의 조율 규칙(pipeline.py)은 상담 요약 에이전트를 부를 조건만 판단해 기록한다.
"""

from typing import Protocol

from moru.schemas import Record


class ChatAgent(Protocol):
    """부모의 질문 → retrieve.search()로 기간 내 기록 검색 → 근거를 인용해 답한다."""

    def answer(self, child_id: str, question: str, start: str, end: str) -> tuple[str, list[Record]]: ...


class CounselSummaryAgent(Protocol):
    """우려가 2주 이상 이어진 영역의 결과와 근거를 상담사에게 넘길 요약으로 만든다."""

    def summarize(self, child_id: str, domain: str, weeks: list[dict]) -> str: ...


class NotImplementedChat:
    def answer(self, child_id, question, start, end):
        raise NotImplementedError("채팅 에이전트는 기획만 했습니다(README '구현 범위').")


class NotImplementedCounsel:
    def summarize(self, child_id, domain, weeks):
        raise NotImplementedError("상담 요약 에이전트는 기획만 했습니다(README '구현 범위').")
