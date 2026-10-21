"""음성 코칭 Pydantic 스키마 단위 테스트."""

from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from schemas.voice_cue import VoiceCueBase, VoiceCueResponse


def make_cue(**overrides):
    """테스트용 기본 음성 데이터 생성."""
    data = {
        "category": "TRACKING",
        "exercise_id": None,
        "exercise_step_id": None,
        "event_code": "USER_LOST",
        "audio_url": "/audio/pose/common/user_lost.mp3",
        "is_active": True,
        "message": "화면 안으로 돌아와 주세요.",
    }
    data.update(overrides)
    return data


def test_tracking_common_cue():
    cue = VoiceCueBase(**make_cue())

    assert cue.category == "TRACKING"
    assert cue.exercise_id is None
    assert cue.exercise_step_id is None


def test_exercise_cue():
    cue = VoiceCueBase(
        **make_cue(
            category="EXERCISE",
            exercise_id=1,
            event_code="KNEE_TOO_BENT",
        )
    )

    assert cue.exercise_id == 1
    assert cue.event_code == "KNEE_TOO_BENT"


def test_study_step_cue():
    cue = VoiceCueBase(
        **make_cue(
            category="STUDY",
            exercise_id=1,
            exercise_step_id=3,
            event_code="STEP_CORRECTION",
        )
    )

    assert cue.exercise_step_id == 3


def test_step_id_without_exercise_id_rejected():
    with pytest.raises(ValidationError):
        VoiceCueBase(
            **make_cue(
                category="STUDY",
                exercise_id=None,
                exercise_step_id=3,
            )
        )


def test_tracking_with_exercise_id_rejected():
    with pytest.raises(ValidationError):
        VoiceCueBase(
            **make_cue(
                category="TRACKING",
                exercise_id=1,
            )
        )


def test_exercise_with_step_id_rejected():
    with pytest.raises(ValidationError):
        VoiceCueBase(
            **make_cue(
                category="EXERCISE",
                exercise_id=1,
                exercise_step_id=3,
            )
        )


def test_invalid_category_rejected():
    with pytest.raises(ValidationError):
        VoiceCueBase(**make_cue(category="YOLO"))


def test_empty_audio_url_rejected():
    with pytest.raises(ValidationError):
        VoiceCueBase(**make_cue(audio_url=""))


def test_response_schema():
    now = datetime.now(timezone.utc)

    cue = VoiceCueResponse(
        **make_cue(),
        id=1,
        created_at=now,
        modified_at=now,
    )

    assert cue.id == 1
    assert cue.created_at == now
    assert cue.model_dump()["event_code"] == "USER_LOST"
