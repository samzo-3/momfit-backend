"""음성 코칭 목록 선택 서비스."""

from sqlalchemy.orm import Session

from models.voice_cue import VoiceCue
from repositories import voice_cue_repository


def _scope_priority(cue: VoiceCue) -> int:
    """음성이 적용되는 범위의 구체성 점수를 반환한다."""
    if cue.exercise_step_id is not None:
        return 3

    if cue.exercise_id is not None:
        return 2

    return 1


def select_preferred_cues(cues: list[VoiceCue]) -> list[VoiceCue]:
    """같은 카테고리·이벤트의 음성 중 가장 구체적인 음성을 선택한다.

    event_code가 NULL인 일반 안내는 별개의 레코드로 취급한다.
    """
    selected: dict[tuple[str, str], VoiceCue] = {}
    general_cues: list[VoiceCue] = []

    for cue in cues:
        if cue.event_code is None:
            general_cues.append(cue)
            continue

        key = (cue.category, cue.event_code)
        current = selected.get(key)

        if current is None or _scope_priority(cue) > _scope_priority(current):
            selected[key] = cue

    return sorted(
        [*selected.values(), *general_cues],
        key=lambda cue: cue.id,
    )


def get_voice_cues(
    db: Session,
    *,
    category: str,
    exercise_id: int | None = None,
    exercise_step_id: int | None = None,
) -> list[VoiceCue]:
    """현재 운동·STEP에 적용되는 활성 음성을 반환한다."""
    cues = voice_cue_repository.list_active_by_scope(
        db,
        category=category,
        exercise_id=exercise_id,
        exercise_step_id=exercise_step_id,
    )

    return select_preferred_cues(cues)
