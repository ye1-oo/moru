"""경로, 모델 ID, 영역 매핑 등 프로젝트 공통 설정."""

import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]
load_dotenv(ROOT / ".env")

DATA_DIR = ROOT / "data"
KDST_DIR = DATA_DIR / "kdst"
DIARY_DIR = DATA_DIR / "diaries"
GOLD_DIR = DATA_DIR / "gold"
LABELS_CSV = DATA_DIR / "videos" / "labels.csv"
CACHE_DIR = ROOT / "cache"
QDRANT_DIR = ROOT / "qdrant_storage"
RESULTS_DIR = ROOT / "results"

GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-3.6-flash")
KURE_MODEL = "nlpai-lab/KURE-v2"
BGE_MODEL = "BAAI/bge-m3"
KURE_DIM = 128

TOP_K = 3
ABSTAIN_DOMAIN_RATIO = 0.5  # 판단 보류 문항이 이 비율 이상이면 영역은 "정보 부족"
MAX_RETRIES = 2

# 영상 폴더 이름(한글)이 곧 영역 라벨이다.
DOMAIN_SLUGS = {
    "대근육": "gross_motor",
    "소근육": "fine_motor",
    "인지": "cognition",
    "언어": "language",
    "사회성": "social",
    "자조": "self_care",
}


def video_dir() -> Path:
    """VIDEO_DIR을 읽는다. 값이 없거나 폴더가 없으면 바로 실패시킨다."""
    value = os.environ.get("VIDEO_DIR")
    if not value:
        raise RuntimeError("VIDEO_DIR이 비어 있습니다. .env.example을 .env로 복사해 채워주세요.")
    path = Path(value).expanduser()
    if not path.is_dir():
        raise RuntimeError(f"영상 폴더를 찾을 수 없습니다: {path}")
    return path


# 무료 등급 호출 설정. 3.8과 3.6 Flash 모두 일일 한도는 모델별 20회다(2026-11-07 429로 확인).
GEMINI_RPM = float(os.environ.get("GEMINI_RPM", "5"))
GEMINI_RPD = int(os.environ.get("GEMINI_RPD", "20"))
THINKING_LEVEL = "low"  # 3.8 Flash는 low, medium, high만 받는다
LLM_CACHE_DIR = CACHE_DIR / "llm"
LLM_LOG = CACHE_DIR / "llm_calls.jsonl"
