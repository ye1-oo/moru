"""정답 라벨 고정(2026-11-08). 이후 수정 금지. 수정 이력: 2026-11-07 1차 실행 후 fine_motor_05 보완 1회."""

import hashlib

from moru import config

FROZEN = {
    "child_A_weekly.csv": "b97f3223fb97e2a02588981ebc0c516e5814264a88565a6f2cacf59cf0fe812c",
    "child_A_relevance.csv": "d0bad7e16d09f3dad97e92244d34bf567004542de5b5a57947ecde2335d86204",
}


def test_gold_files_are_frozen():
    for name, digest in FROZEN.items():
        assert hashlib.sha256((config.GOLD_DIR / name).read_bytes()).hexdigest() == digest, f"{name}이 바뀌었습니다"
