import pandas as pd

from moru import context, evaluate, report
from moru.context import Toggles
from moru.schemas import Evidence, ItemScore, KdstItem, Record
from moru.score import _contains, _norm

ITEMS = [KdstItem(item_id="x_gm_01", age_band="x", domain="gross_motor", text="공을 찬다"),
         KdstItem(item_id="x_lg_01", age_band="x", domain="language", text="단어를 말한다")]
REC = Record(diary_id="d1", date="2026-10-20", age_months=18, parent_text="공놀이를 했다.", caption_text="아이가 공을 발로 찬다.")
EV = [Evidence(item_id="x_gm_01", records=[REC]), Evidence(item_id="x_lg_01", records=[])]


def build(t):
    return context.scoring_context(ITEMS, EV, 18, "2026-10-19", "2026-10-25", t)


def test_full_context_has_tags_and_rule():
    text = build(Toggles())
    assert "2026-10-20 (생후 18개월)" in text
    assert "[부모 일기]" in text and "[미디어 캡셔닝 내용]" in text
    assert "판단 보류" in text
    assert "(검색된 기록 없음)" in text


def test_toggles_remove_each_element():
    assert "2026-10-20" not in build(Toggles(use_date_tags=False))
    no_source = build(Toggles(use_source_tags=False))
    assert "[부모 일기]" not in no_source and "공놀이를 했다. 아이가 공을 발로 찬다." in no_source
    assert "판단 보류" not in build(Toggles(use_abstain_rule=False))


def test_mask_hides_item_text():
    masked = context.mask_items(build(Toggles()), ITEMS)
    assert "공을 찬다" not in masked and "〈문항 원문 비공개: x_gm_01〉" in masked


def test_quote_match_allows_small_typo_only():
    text = _norm("아이는 스스로 칫솔질을 하고 물을 뱉어냅니다.")
    assert _contains(_norm("아는 스스로 칫솔질을 하고 물을 뱉어냅니다."), text)
    assert not _contains(_norm("아이가 블록을 쌓는다."), text)


def score(item_id, value, quote=None):
    return ItemScore(item_id=item_id, score=value, evidence_quote=quote, evidence_date="2026-10-20" if quote else None,
                     source="caption" if quote else None, confidence=0.9)


def test_domain_status_and_concern():
    items = [KdstItem(item_id=f"g{i}", age_band="x", domain="gross_motor", text=str(i)) for i in range(4)]
    domains = report.aggregate(items, [score("g0", 1, "q"), score("g1", None), score("g2", None), score("g3", 3, "q")])
    assert domains[0]["status"] == "정보 부족" and domains[0]["concern"]
    assert domains[0]["total"] == 4 and domains[0]["max_scored"] == 6


def test_metrics_hallucination_and_abstain():
    table = pd.DataFrame([
        {"gold": 2, "pred": 2, "quote_found": True, "date_match": True, "source_match": True, "inconsistent": False, "confidence": .9, "retrieved_gold": None},
        {"gold": None, "pred": 1, "quote_found": False, "date_match": None, "source_match": None, "inconsistent": False, "confidence": .5, "retrieved_gold": None},
        {"gold": None, "pred": None, "quote_found": None, "date_match": None, "source_match": None, "inconsistent": False, "confidence": 0, "retrieved_gold": None},
    ])
    m = evaluate.metrics(table)
    assert m["환각 비율"] == 0.5 and m["판단 보류 재현율"] == 0.5 and m["정확 일치"] == 1.0
    assert m["근거 추적 정확도"] == 0.5
