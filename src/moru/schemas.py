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
    """영상 1개 캡셔닝 출력(단독 호출)."""

    caption_text: str = Field(description="관찰된 행동을 해석 없이 객관적으로 묘사한 한국어 문장들")


class VideoCaption(BaseModel):
    video_number: int = Field(description="[영상 N]의 번호 N")
    caption_text: str = Field(description="이 영상에서만 관찰된 행동을 객관적으로 묘사한 한국어 문장들")


class CaptionBatch(BaseModel):
    """영상 여러 개를 한 번에 보낼 때의 출력. 무료 한도 때문에 묶어서 호출한다."""

    captions: list[VideoCaption]


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


# ------------------------------------------------------------------ 에이전트 입출력
# 역할 분리형 멀티 에이전트 파이프라인: 캡션 → 검색 → 채점 → 리포트 → (조건부) 체크리스트.
# 채점·리포트·체크리스트 에이전트의 LLM 출력은 아래 *Output 스키마로 받는다. 스키마는
# 일부러 느슨하게 두고(점수-근거 일관성은 강제하지 않음), 규칙 위반은 evaluate.py가 지표로 센다.
# 강제하면 "판단 보류 규칙 제거" 조건에서 검증 실패 재시도가 한도를 소모하기 때문이다.


class Record(BaseModel):
    """검색 에이전트가 돌려주는 근거 기록(일기 한 편 = 청크 하나)."""

    diary_id: str
    date: str
    age_months: int
    parent_text: str
    caption_text: str
    score: float | None = None  # 검색 유사도(MaxSim)


class Evidence(BaseModel):
    """검색 에이전트의 출력: 문항별 근거 기록."""

    item_id: str
    records: list[Record]


class ItemScore(BaseModel):
    item_id: str
    score: int | None = Field(description="0~3 정수 또는 null")
    evidence_quote: str | None = Field(description="근거 기록에서 그대로 옮긴 문장")
    evidence_date: str | None = Field(description="근거 기록의 날짜 YYYY-MM-DD")
    source: Source | None = Field(description="parent 또는 caption")
    confidence: float = Field(description="0~1")


class ScoringOutput(BaseModel):
    """채점 에이전트(와 단일 에이전트)의 출력."""

    items: list[ItemScore]


class ForcedItemScore(BaseModel):
    """'판단 보류 불가' 기준선: 점수는 반드시 0~3 정수."""

    item_id: str
    score: int = Field(description="0~3 정수(필수)")
    evidence_quote: str | None = Field(description="근거 기록에서 그대로 옮긴 문장")
    evidence_date: str | None = Field(description="근거 기록의 날짜 YYYY-MM-DD")
    source: Source | None = Field(description="parent 또는 caption")
    confidence: float = Field(description="0~1")


class ForcedScoringOutput(BaseModel):
    items: list[ForcedItemScore]


class DomainNote(BaseModel):
    domain: Domain
    note: str = Field(description="이 영역에 대한 한두 문장")


class ReportOutput(BaseModel):
    """리포트 에이전트의 출력: 종합 소견."""

    summary: str = Field(description="3~5문장 종합 소견. 진단처럼 단정하지 않는다")
    domain_notes: list[DomainNote]


class ChecklistBehavior(BaseModel):
    observe: str = Field(description="집에서 관찰해 볼 대표 행동 한 문장(검사 문항을 그대로 옮기지 않음)")
    play: str = Field(description="그 행동을 자연스럽게 볼 수 있는 놀이 한 문장")


class ChecklistDomain(BaseModel):
    domain: Domain
    behaviors: list[ChecklistBehavior] = Field(description="대표 관찰 행동 2~3개")


class ChecklistOutput(BaseModel):
    """체크리스트 에이전트의 출력. 정보 부족 영역마다 대표 관찰 행동 2~3개(2026-11-08 축약)."""

    domains: list[ChecklistDomain]
