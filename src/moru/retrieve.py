"""검색 에이전트 (명세 4.2). LLM을 쓰지 않는다.

입력: 문항 목록, child_id, 평가 기간, top-k
출력: 문항별 근거 기록 list[Evidence]

- per_item(기본): 문항 하나하나를 질문으로 검색한다.
- batched(비교 ④): 영역 문항을 하나의 질문으로 합쳐 한 번 검색한다. 가져오는 개수는
  같은 영역에서 문항별 검색이 가져온 서로 다른 기록 수와 같게 맞추고, 그 기록을 영역의
  모든 문항에 똑같이 붙인다.

채팅·상담 에이전트도 이 모듈의 search()를 그대로 쓰도록 설계했다(interfaces.py).
"""

from collections import defaultdict
from datetime import date as Date

from qdrant_client import QdrantClient

from moru import config, embed, index
from moru.schemas import Evidence, KdstItem, Record


def search(qdrant: QdrantClient, collection: str, query: str, child_id: str,
           start: Date, end: Date, k: int, model: str = "kure") -> list[Record]:
    """질문 하나로 기간 안의 기록을 찾는다. 채팅 에이전트가 재사용할 공용 함수."""
    vector = embed.encode([query], model, "query")[0]
    using = "colbert" if model == "kure" else "dense"
    hits = qdrant.query_points(
        collection, query=vector.tolist(), using=using, limit=k,
        query_filter=index.period_filter(child_id, start, end), with_payload=True,
    ).points
    return [Record(diary_id=h.payload["diary_id"], date=h.payload["date"], age_months=h.payload["age_months"],
                   parent_text=h.payload["parent_text"], caption_text=h.payload["caption_text"], score=h.score)
            for h in hits]


def per_item(qdrant, collection, items: list[KdstItem], child_id, start, end,
             k: int = config.TOP_K, model: str = "kure") -> list[Evidence]:
    return [Evidence(item_id=item.item_id,
                     records=search(qdrant, collection, item.text, child_id, start, end, k, model))
            for item in items]


def batched(qdrant, collection, items: list[KdstItem], child_id, start, end,
            k: int = config.TOP_K, model: str = "kure") -> list[Evidence]:
    reference = per_item(qdrant, collection, items, child_id, start, end, k, model)
    by_domain: dict[str, list[KdstItem]] = defaultdict(list)
    for item in items:
        by_domain[item.domain].append(item)
    unique = defaultdict(set)
    for item, ev in zip(items, reference):
        unique[item.domain].update(r.diary_id for r in ev.records)
    out = {}
    for domain, group in by_domain.items():
        query = " ".join(item.text for item in group)
        records = search(qdrant, collection, query, child_id, start, end, len(unique[domain]), model)
        for item in group:
            out[item.item_id] = Evidence(item_id=item.item_id, records=records)
    return [out[item.item_id] for item in items]
