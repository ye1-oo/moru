"""채점 에이전트와 단일 에이전트(비교 ①) (명세 4.4).

호출 단위는 주차다(무료 한도 때문에 한 주의 모든 영역을 한 번에 채점).
LLM 출력은 느슨한 ScoringOutput으로 받고, 아래 check는 "모든 문항이 한 번씩 있는가"만 강제한다.
점수 범위·null 일관성·근거 실재 여부는 flags로 남겨 evaluate.py가 지표로 센다.
"""

from pathlib import Path

from moru import llm
from moru.schemas import Diary, ItemScore, KdstItem, ScoringOutput


def _check_ids(item_ids: list[str]):
    def check(result: ScoringOutput) -> None:
        returned = sorted(i.item_id for i in result.items)
        if returned != sorted(item_ids):
            missing = set(item_ids) - set(returned)
            raise ValueError(f"문항이 맞지 않습니다. 빠짐 {sorted(missing)[:5]}, 반환 {len(returned)}개")
    return check


def scoring_agent(prompt: str, items: list[KdstItem], repeat: int = 0, tag: str = "score") -> list[ItemScore]:
    result = llm.generate(prompt, schema=ScoringOutput, check=_check_ids([i.item_id for i in items]),
                          repeat=repeat, tag=tag)
    return result.items


def single_agent(prompt: str, items: list[KdstItem], videos: list[Path], repeat: int = 0) -> list[ItemScore]:
    result = llm.generate(prompt, schema=ScoringOutput, videos=videos,
                          check=_check_ids([i.item_id for i in items]), repeat=repeat, tag="single_agent")
    return result.items


def _norm(text: str) -> str:
    return "".join(ch for ch in text if ch.isalnum())


def _contains(quote: str, text: str, threshold: float = 0.9) -> bool:
    """근거 문장이 기록에 있는지. 한두 글자 옮겨 적기 오류(예: '아이는'→'아는')는 허용한다."""
    if not quote or not text:
        return False
    if quote in text:
        return True
    from difflib import SequenceMatcher

    # 같은 길이의 구간을 옮겨 가며 비교한다. 흩어진 글자가 우연히 맞는 경우를 막기 위해서다.
    n = len(quote)
    for start in range(0, max(1, len(text) - n + 2)):
        window = text[start : start + n + 2]
        if SequenceMatcher(None, quote, window, autojunk=False).ratio() >= threshold:
            return True
    return False


def flags(score: ItemScore, diaries: list[Diary], captions: dict[str, str]) -> dict:
    """규칙 위반과 근거 추적 결과. quote_found: 근거 문장이 실제 기록에 있다.
    date_match: 근거 날짜가 그 문장이 있는 기록의 날짜와 같다. source_match: 출처가 맞다."""
    out = {"out_of_range": score.score is not None and not 0 <= score.score <= 3,
           "inconsistent": (score.score is None) != (score.evidence_quote is None),
           "quote_found": None, "date_match": None, "source_match": None, "found_in": None}
    if score.evidence_quote:
        quote = _norm(score.evidence_quote)
        hits = []
        for d in diaries:
            caption = " ".join(captions.get(v, "") for v in d.media)
            if _contains(quote, _norm(d.parent_text)):
                hits.append((d, "parent"))
            if _contains(quote, _norm(caption)):
                hits.append((d, "caption"))
        out["quote_found"] = bool(hits)
        if hits:
            out["found_in"] = ";".join(f"{d.diary_id}:{s}" for d, s in hits)
            out["date_match"] = any(d.date.isoformat() == score.evidence_date for d, _ in hits)
            out["source_match"] = any(s == score.source for _, s in hits)
    return out
