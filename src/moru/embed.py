"""KURE-v2(멀티벡터, PyLate)와 BGE-M3(단일 dense 벡터) 임베딩 래퍼.

임베딩은 cache/embeddings/에 텍스트 해시로 저장해 같은 텍스트를 다시 계산하지 않는다.
"""

import hashlib
from functools import lru_cache

import numpy as np

from moru import config

EMBED_CACHE = config.CACHE_DIR / "embeddings"


@lru_cache(maxsize=2)
def _model(name: str):
    if name == "kure":
        from pylate import models

        return models.ColBERT(model_name_or_path=config.KURE_MODEL, device="cpu")
    if name == "bge":
        from sentence_transformers import SentenceTransformer

        return SentenceTransformer(config.BGE_MODEL, device="cpu")
    raise ValueError(name)


def _key(name: str, kind: str, text: str) -> str:
    return hashlib.sha256(f"{name}|{kind}|{text}".encode()).hexdigest()


def encode(texts: list[str], name: str = "kure", kind: str = "document") -> list[np.ndarray]:
    """kind는 document 또는 query. KURE는 토큰별 벡터 행렬, BGE는 벡터 1개를 돌려준다."""
    EMBED_CACHE.mkdir(parents=True, exist_ok=True)
    out: list[np.ndarray | None] = []
    missing = []
    for i, text in enumerate(texts):
        path = EMBED_CACHE / f"{_key(name, kind, text)}.npy"
        if path.exists():
            out.append(np.load(path))
        else:
            out.append(None)
            missing.append(i)
    if missing:
        model = _model(name)
        batch = [texts[i] for i in missing]
        if name == "kure":
            vectors = model.encode(batch, is_query=(kind == "query"), batch_size=16, show_progress_bar=False)
        else:
            vectors = model.encode(batch, normalize_embeddings=True, batch_size=16, show_progress_bar=False)
        for i, vector in zip(missing, vectors):
            vector = np.asarray(vector, dtype=np.float32)
            np.save(EMBED_CACHE / f"{_key(name, kind, texts[i])}.npy", vector)
            out[i] = vector
    return out  # type: ignore[return-value]
