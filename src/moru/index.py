"""일기 청크를 조립하고 임베딩해 Qdrant에 저장한다 (명세 4.1).

일기 한 편 = 청크 하나. 부모 글과 영상 캡션을 함께 넣고, 각각은 payload에도 따로 저장한다.
content는 비교 실험 ③용이다: both(기본), parent(일기만), caption(캡션만).
"""

import json
import uuid
from datetime import date as Date
from pathlib import Path
from typing import Literal

from qdrant_client import QdrantClient, models

from moru import config, embed
from moru.schemas import Diary

Content = Literal["both", "parent", "caption"]
CAPTION_FILE = config.RESULTS_DIR / "raw" / f"captions_{config.GEMINI_MODEL}_item_conditioned.jsonl"


def load_diaries(path: Path) -> list[Diary]:
    return [Diary.model_validate_json(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def load_captions(path: Path = CAPTION_FILE) -> dict[str, str]:
    """실험 A에서 만든 캡션을 재사용한다. 캡션은 인덱싱 때 한 번만 만든다."""
    if not path.exists():
        return {}
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    return {row["video_id"]: row["caption"] for row in rows}


def caption_text(diary: Diary, captions: dict[str, str]) -> str:
    missing = [v for v in diary.media if v not in captions]
    if missing:
        raise KeyError(f"{diary.diary_id}: 캡션이 없는 영상 {missing}")
    return " ".join(captions[v] for v in diary.media)


def chunk_text(diary: Diary, caption: str, content: Content = "both") -> str:
    """임베딩할 청크 텍스트. 명세 4.1의 형식을 따른다."""
    lines = [f"{diary.date.isoformat()} (생후 {diary.age_months}개월)"]
    if content in ("both", "parent") and diary.parent_text:
        lines.append(f"[부모 일기] {diary.parent_text}")
    if content in ("both", "caption") and caption:
        lines.append(f"[미디어 캡셔닝 내용] {caption}")
    return "\n".join(lines)


def collection_name(model: str, content: Content) -> str:
    return f"diaries_{model}_{content}"


def client(path: Path = config.QDRANT_DIR) -> QdrantClient:
    return QdrantClient(path=str(path))


def build(qdrant: QdrantClient, diaries: list[Diary], captions: dict[str, str],
          model: str = "kure", content: Content = "both") -> str:
    """컬렉션을 새로 만들고 청크를 넣는다. 내용이 없는 청크(예: 캡션만인데 영상 없음)는 뺀다."""
    name = collection_name(model, content)
    payloads, texts = [], []
    for diary in diaries:
        caption = caption_text(diary, captions)
        if content == "caption" and not caption:
            continue
        if content == "parent" and not diary.parent_text:
            continue
        text = chunk_text(diary, caption, content)
        texts.append(text)
        payloads.append({
            "diary_id": diary.diary_id, "child_id": diary.child_id, "date": diary.date.isoformat(),
            "date_ord": diary.date.toordinal(), "age_months": diary.age_months,
            "parent_text": diary.parent_text if content != "caption" else "",
            "caption_text": caption if content != "parent" else "",
            "has_media": bool(diary.media), "chunk_text": text,
        })
    vectors = embed.encode(texts, model, "document")
    if qdrant.collection_exists(name):
        qdrant.delete_collection(name)
    if model == "kure":
        qdrant.create_collection(name, vectors_config={"colbert": models.VectorParams(
            size=config.KURE_DIM, distance=models.Distance.COSINE,
            multivector_config=models.MultiVectorConfig(comparator=models.MultiVectorComparator.MAX_SIM),
            hnsw_config=models.HnswConfigDiff(m=0))})
        points = [models.PointStruct(id=_uid(p["diary_id"]), vector={"colbert": v.tolist()}, payload=p)
                  for p, v in zip(payloads, vectors)]
    else:
        qdrant.create_collection(name, vectors_config={"dense": models.VectorParams(
            size=len(vectors[0]), distance=models.Distance.COSINE)})
        points = [models.PointStruct(id=_uid(p["diary_id"]), vector={"dense": v.tolist()}, payload=p)
                  for p, v in zip(payloads, vectors)]
    qdrant.upsert(name, points)
    return name


def _uid(diary_id: str) -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_URL, diary_id))


def period_filter(child_id: str, start: Date, end: Date) -> models.Filter:
    return models.Filter(must=[
        models.FieldCondition(key="child_id", match=models.MatchValue(value=child_id)),
        models.FieldCondition(key="date_ord", range=models.Range(gte=start.toordinal(), lte=end.toordinal())),
    ])
