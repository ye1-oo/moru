"""정답 라벨 고정(2026-11-08). 이후 수정 금지. 수정 이력: 2026-11-07 1차 실행 후 fine_motor_05 보완 1회."""

import hashlib

from moru import config

FROZEN = {
    "child_A_weekly.csv": "b97f3223fb97e2a02588981ebc0c516e5814264a88565a6f2cacf59cf0fe812c",
    "child_A_relevance.csv": "d0bad7e16d09f3dad97e92244d34bf567004542de5b5a57947ecde2335d86204",
    # 3주차(촘촘한 기록 1주): 2026-11-10 실행 전에 고정
    "child_A_w3_weekly.csv": "3310e5c0855bf741296cd90fa67694a7b4d53891152d8aafba61f00ca4240cd1",
    "child_A_w3_relevance.csv": "fec643d24d9a2731ba8660285997dddffbb62532aa594fabdcc7ace10bea69ff",
}


def test_gold_files_are_frozen():
    for name, digest in FROZEN.items():
        assert hashlib.sha256((config.GOLD_DIR / name).read_bytes()).hexdigest() == digest, f"{name}이 바뀌었습니다"
