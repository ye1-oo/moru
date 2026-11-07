from moru.caption import build_prompt, first_per_domain, load_videos
from moru.config import LABELS_CSV
from moru.schemas import KdstItem

import pytest

ITEMS = [
    KdstItem(item_id=f"x_{domain}", age_band="x", domain=domain, text=f"{domain} 행동 문장")
    for domain in ["gross_motor", "fine_motor", "cognition", "language", "social", "self_care"]
]
LABEL_WORDS = ["대근육", "소근육", "인지", "언어", "사회성", "자조"]


def test_item_prompt_has_all_domains_without_domain_names():
    prompt = build_prompt("item_conditioned", ITEMS, None)
    assert all(item.text in prompt for item in ITEMS)
    assert not any(word in prompt for word in LABEL_WORDS)


def test_generic_prompt_has_no_items():
    prompt = build_prompt("generic", ITEMS, None)
    assert not any(item.text in prompt for item in ITEMS)


@pytest.mark.skipif(not LABELS_CSV.exists(), reason="로컬 labels.csv 필요")
def test_duplicate_video_is_excluded():
    videos = load_videos()
    assert len(videos) == 98
    assert "self_care_15" not in set(videos["video_id"])


@pytest.mark.skipif(not LABELS_CSV.exists(), reason="로컬 labels.csv 필요")
def test_first_per_domain_picks_five_each():
    picked = first_per_domain(load_videos(), 5)
    assert len(picked) == 30
    assert set(picked["domain"].value_counts()) == {5}


def fake_generate(payload, retries):
    """llm.generate처럼 check를 호출하고, 실패하면 재시도한다."""
    from moru.schemas import CaptionBatch

    def generate(prompt, *, schema, videos, check, tag):
        for attempt in payload:
            result = CaptionBatch.model_validate(attempt)
            try:
                check(result)
                return result
            except ValueError:
                retries.append(1)
        raise ValueError("재시도 초과")

    return generate


def batch_rows():
    return [{"video_id": f"v{i}", "file": "x/y.mp4"} for i in range(1, 4)]


def captions_for(*numbers):
    return {"captions": [{"video_number": n, "caption_text": f"캡션{n}"} for n in numbers]}


def test_caption_batch_maps_numbers_to_videos(monkeypatch):
    from moru import caption, llm

    monkeypatch.setattr(caption, "video_path", lambda relative: relative)
    monkeypatch.setattr(llm, "generate", fake_generate([captions_for(3, 1, 2)], []))
    result = caption.caption_batch(batch_rows(), "generic", [])
    assert result == {"v1": "캡션1", "v2": "캡션2", "v3": "캡션3"}


def test_caption_batch_retries_when_a_video_is_missing(monkeypatch):
    from moru import caption, llm

    retries = []
    monkeypatch.setattr(caption, "video_path", lambda relative: relative)
    monkeypatch.setattr(llm, "generate", fake_generate([captions_for(1, 2), captions_for(1, 2, 3)], retries))
    assert len(caption.caption_batch(batch_rows(), "generic", [])) == 3
    assert retries == [1]
