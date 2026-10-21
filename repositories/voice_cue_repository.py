"""voice_cues 테이블 조회."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from models.voice_cue import VoiceCue


def list_active_by_scope(
    db: Session,
    *,
    category: str,
    exercise_id: int | None = None,
    exercise_step_id: int | None = None,
) -> list[VoiceCue]:
    """카테고리와 운동·STEP 범위에 해당하는 활성 음성 목록을 조회한다.

    조회 범위:
    - TRACKING: 전체 공통 음성
    - EXERCISE: 전체 공통 + 운동별 음성
    - STUDY: 전체 공통 + 운동별 공통 + STEP별 음성

    이벤트 중복 제거 및 우선순위 선택은 Service에서 처리한다.
    """

    conditions = [
        VoiceCue.is_active.is_(True),
        VoiceCue.category == category,
    ]

    if category == "TRACKING":
        conditions.extend(
            [
                VoiceCue.exercise_id.is_(None),
                VoiceCue.exercise_step_id.is_(None),
            ]
        )

    elif category == "EXERCISE":
        conditions.append(VoiceCue.exercise_step_id.is_(None))

        if exercise_id is None:
            conditions.append(VoiceCue.exercise_id.is_(None))
        else:
            conditions.append(
                VoiceCue.exercise_id.in_([exercise_id])
                | VoiceCue.exercise_id.is_(None)
            )

    elif category == "STUDY":
        if exercise_id is None:
            conditions.extend(
                [
                    VoiceCue.exercise_id.is_(None),
                    VoiceCue.exercise_step_id.is_(None),
                ]
            )
        else:
            conditions.append(
                VoiceCue.exercise_id.in_([exercise_id])
                | VoiceCue.exercise_id.is_(None)
            )

            if exercise_step_id is None:
                conditions.append(VoiceCue.exercise_step_id.is_(None))
            else:
                conditions.append(
                    VoiceCue.exercise_step_id.in_([exercise_step_id])
                    | VoiceCue.exercise_step_id.is_(None)
                )

    else:
        return []

    stmt = (
        select(VoiceCue)
        .where(*conditions)
        .order_by(VoiceCue.id)
    )

    return list(db.scalars(stmt))


def get_active_by_event_code(
    db: Session,
    *,
    category: str,
    event_code: str,
    exercise_id: int | None = None,
    exercise_step_id: int | None = None,
) -> list[VoiceCue]:
    """조회 범위 내 특정 이벤트 코드에 해당하는 활성 음성을 조회한다."""

    cues = list_active_by_scope(
        db,
        category=category,
        exercise_id=exercise_id,
        exercise_step_id=exercise_step_id,
    )

    return [
        cue for cue in cues
        if cue.event_code == event_code
    ]
