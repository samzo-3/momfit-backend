"""음성 코칭 Service의 범위별 우선순위 테스트."""

from models.voice_cue import VoiceCue
from services.pose_coaching.voice_cue_service import select_preferred_cues


def make_cue(
    cue_id: int,
    *,
    category: str = "STUDY",
    event_code: str | None = "STEP_COMPLETED",
    exercise_id: int | None = None,
    exercise_step_id: int | None = None,
) -> VoiceCue:
    """DB 연결 없이 테스트용 ORM 객체를 생성한다."""
    return VoiceCue(
        id=cue_id,
        category=category,
        event_code=event_code,
        exercise_id=exercise_id,
        exercise_step_id=exercise_step_id,
        audio_url=f"/audio/test/{cue_id}.mp3",
        is_active=True,
        message=f"테스트 음성 {cue_id}",
    )


def test_step_cue_has_highest_priority():
    """STEP 전용 > 운동 전용 > 전체 공통."""
    cues = [
        make_cue(1),
        make_cue(2, exercise_id=1),
        make_cue(3, exercise_id=1, exercise_step_id=3),
    ]

    result = select_preferred_cues(cues)

    assert [cue.id for cue in result] == [3]


def test_exercise_cue_overrides_global():
    """STEP 음성이 없으면 운동 전용 음성을 선택한다."""
    cues = [
        make_cue(1),
        make_cue(2, exercise_id=1),
    ]

    result = select_preferred_cues(cues)

    assert [cue.id for cue in result] == [2]


def test_global_cue_fallback():
    """전용 음성이 없으면 전체 공통 음성을 선택한다."""
    result = select_preferred_cues([make_cue(1)])

    assert [cue.id for cue in result] == [1]


def test_different_events_are_preserved():
    """이벤트 코드가 다르면 모두 유지한다."""
    cues = [
        make_cue(1, event_code="STEP_STARTED"),
        make_cue(2, event_code="STEP_COMPLETED"),
    ]

    result = select_preferred_cues(cues)

    assert [cue.id for cue in result] == [1, 2]


def test_null_event_codes_are_preserved():
    """event_code가 NULL인 일반 안내는 중복 제거하지 않는다."""
    cues = [
        make_cue(1, event_code=None),
        make_cue(2, event_code=None),
    ]

    result = select_preferred_cues(cues)

    assert [cue.id for cue in result] == [1, 2]


def test_same_event_different_categories():
    """이벤트 코드가 같아도 카테고리가 다르면 유지한다."""
    cues = [
        make_cue(
            1,
            category="EXERCISE",
            event_code="COMPLETED",
            exercise_id=1,
        ),
        make_cue(
            2,
            category="STUDY",
            event_code="COMPLETED",
            exercise_id=1,
        ),
    ]

    result = select_preferred_cues(cues)

    assert [cue.id for cue in result] == [1, 2]


def test_result_is_sorted_by_id():
    """조회 입력 순서와 관계없이 ID 순서로 반환한다."""
    cues = [
        make_cue(5, event_code="EVENT_5"),
        make_cue(2, event_code="EVENT_2"),
        make_cue(3, event_code="EVENT_3"),
    ]

    result = select_preferred_cues(cues)

    assert [cue.id for cue in result] == [2, 3, 5]
