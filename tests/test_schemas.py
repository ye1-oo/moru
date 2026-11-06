import json

import pytest
from pydantic import ValidationError

from moru.config import DATA_DIR
from moru.schemas import Diary, ItemResult, KdstItem

SCORED = dict(
    item_id="x", score=2, evidence_quote="문장", evidence_date="2026-10-29",
    source="parent", confidence=0.8,
)
ABSTAIN = dict(
    item_id="x", score=None, evidence_quote=None, evidence_date=None,
    source=None, confidence=0.2,
)


def test_valid_results():
    ItemResult(**SCORED)
    ItemResult(**ABSTAIN)


@pytest.mark.parametrize(
    "changes",
    [
        {"score": 4},
        {"score": -1},
        {"evidence_quote": None},
        {"source": None},
        {"evidence_date": "10월 29일"},
        {"confidence": 1.5},
    ],
)
def test_invalid_scored(changes):
    with pytest.raises(ValidationError):
        ItemResult(**{**SCORED, **changes})


def test_abstain_must_have_no_evidence():
    with pytest.raises(ValidationError):
        ItemResult(**{**ABSTAIN, "evidence_quote": "문장"})


def test_example_files_parse():
    for item in json.loads((DATA_DIR / "kdst/example.json").read_text(encoding="utf-8")):
        KdstItem(**item)
    for line in (DATA_DIR / "diaries/example.jsonl").read_text(encoding="utf-8").splitlines():
        Diary.model_validate_json(line)
