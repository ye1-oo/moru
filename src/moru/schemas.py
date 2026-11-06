"""입력 데이터와 LLM 출력의 Pydantic 스키마.

아래 검증기는 Gemini 스키마로 강제되지 않으므로, 응답을 받은 뒤 파이썬에서
model_validate_json()으로 확인한다. 실패하면 llm.py가 재시도한다.
"""

from datetime import date as Date
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

Domain = Literal["gross_motor", "fine_motor", "cognition", "language", "social", "self_care"]
Source = Literal["parent", "caption"]
CaptionMode = Literal["item_conditioned", "generic"]


class KdstItem(BaseModel):
    """data/kdst/{age_band}.json의 한 줄."""

    item_id: str
    age_band: str
    domain: Domain
    text: str


class Diary(BaseModel):
    """data/diaries/*.jsonl의 한 줄."""

    diary_id: str
    child_id: str
    date: Date
    age_months: int = Field(ge=0)
    parent_text: str
    media: list[str] = []


class Caption(BaseModel):
    """캡셔닝 LLM의 출력. 부모 일기는 입력에 넣지 않는다."""

    caption_text: str = Field(description="관찰된 행동을 해석 없이 객관적으로 묘사한 한국어 문장들")


class ItemResult(BaseModel):
    """문항 하나의 채점 결과. score가 None이면 판단 보류(화면 표기: 정보 없음)."""

    item_id: str
    score: int | None = Field(ge=0, le=3, description="0~3. 근거가 없으면 null")
    evidence_quote: str | None = Field(description="근거 기록에서 그대로 옮긴 문장")
    evidence_date: str | None = Field(description="근거 기록의 날짜 YYYY-MM-DD")
    source: Source | None
    confidence: float = Field(ge=0, le=1)

    @field_validator("evidence_date")
    @classmethod
    def check_date(cls, value: str | None) -> str | None:
        if value is not None:
            Date.fromisoformat(value)
        return value

    @model_validator(mode="after")
    def check_null_consistency(self) -> "ItemResult":
        fields = (self.evidence_quote, self.evidence_date, self.source)
        if self.score is not None and any(f is None for f in fields):
            raise ValueError(f"{self.item_id}: 점수가 있으면 근거, 날짜, 출처가 모두 필요합니다")
        if self.score is None and any(f is not None for f in fields):
            raise ValueError(f"{self.item_id}: 판단 보류 문항에는 근거를 적지 않습니다")
        return self


class DomainResult(BaseModel):
    """영역 단위 채점 호출의 출력."""

    domain: Domain
    items: list[ItemResult]
