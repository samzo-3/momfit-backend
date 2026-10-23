from types import SimpleNamespace
from uuid import UUID

import pytest
from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy import event
from sqlalchemy.orm import Session

from api.sidekick_study import get_sidekick_study_config
from models.exercise import Exercise
from models.exercise_criteria_version import ExerciseCriteriaVersion
from models.exercise_step import ExerciseStep
from models.exercise_step_criteria_version import ExerciseStepCriteriaVersion
from models.exercise_step_record import ExerciseStepRecord
from schemas.exercise_step_record import ExerciseStepRecordCreate
from services.pose_coaching.exercise_step_record_service import (
    create_exercise_step_record,
)

SESSION_ID = UUID("12345678-1234-4678-9234-567812345678")


def seed_side_kick(db: Session) -> dict[str, int]:
    @event.listens_for(db, "before_flush")
    def assign_sqlite_step_record_ids(session, _flush_context, _instances) -> None:
        for item in session.new:
            if isinstance(item, ExerciseStepRecord) and item.id is None:
                item.id = 10_000 + session.query(ExerciseStepRecord).count()

    exercise = Exercise(id=10, exercise_name="Side Kick", video_url="/side-kick.mp4")
    other_exercise = Exercise(id=20, exercise_name="Other", video_url="/other.mp4")
    left = ExerciseStep(
        id=101,
        exercise_id=10,
        step_order=1,
        step_name="READY",
        clip_video_url="/left.mp4",
        important=True,
    )
    right = ExerciseStep(
        id=102,
        exercise_id=10,
        step_order=2,
        step_name="LEFT_LIFT",
        clip_video_url="/right.mp4",
        important=True,
    )
    remaining_steps = [
        ExerciseStep(
            id=step_id,
            exercise_id=10,
            step_order=step_order,
            step_name=f"STEP_{step_order}",
            clip_video_url=f"/step-{step_order}.mp4",
            important=True,
        )
        for step_id, step_order in ((103, 3), (104, 4), (105, 5))
    ]
    foreign_step = ExerciseStep(
        id=201,
        exercise_id=20,
        step_order=1,
        step_name="OTHER",
        clip_video_url="/other.mp4",
        important=True,
    )
    criteria = ExerciseCriteriaVersion(
        id=301,
        exercise_id=10,
        evaluation_criteria={},
        criteria_version="1.0.0",
        schema_version=1,
        status="ACTIVE",
    )
    other_criteria = ExerciseCriteriaVersion(
        id=302,
        exercise_id=20,
        evaluation_criteria={},
        criteria_version="1.0.0",
        schema_version=1,
        status="ACTIVE",
    )
    db.add_all([
        exercise,
        other_exercise,
        left,
        right,
        *remaining_steps,
        foreign_step,
        criteria,
        other_criteria,
    ])
    db.flush()
    db.add_all([
        ExerciseStepCriteriaVersion(
            id=401,
            exercise_step_id=101,
            exercise_criteria_version_id=301,
            evaluation_criteria={},
            step_criteria_version="1.0.0",
        ),
        *[
            ExerciseStepCriteriaVersion(
                id=400 + step_id,
                exercise_step_id=step_id,
                exercise_criteria_version_id=301,
                evaluation_criteria={},
                step_criteria_version="1.0.0",
            )
            for step_id in (103, 104, 105)
        ],
        ExerciseStepCriteriaVersion(
            id=402,
            exercise_step_id=102,
            exercise_criteria_version_id=301,
            evaluation_criteria={},
            step_criteria_version="1.0.0",
        ),
    ])
    db.commit()
    return {"exercise": 10, "left": 101, "right": 102, "foreign_step": 201, "criteria": 301, "other_criteria": 302}


def payload(**overrides) -> ExerciseStepRecordCreate:
    values = {
        "exercise_id": 10,
        "exercise_step_id": 101,
        "exercise_criteria_version_id": 301,
        "criteria_version": "1.0.0",
        "step_session_id": SESSION_ID,
        "step_result_status": "PASS",
        "step_score": 80,
        "step_report": {"criteria_version": "1.0.0"},
    }
    values.update(overrides)
    return ExerciseStepRecordCreate(**values)


@pytest.mark.parametrize(
    ("result", "score"),
    [
        ("PASS", None),
        ("NON_PASS", None),
        ("NOT_EVALUATED", None),
        ("PASS", 80),
        ("NON_PASS", 79),
        ("NOT_EVALUATED", 0),
    ],
)
def test_step_result_is_saved_separately_from_record_status(
    db_session: Session, result: str, score: int | None
) -> None:
    seed_side_kick(db_session)

    record = create_exercise_step_record(
        db_session, user_id=1, payload=payload(step_result_status=result, step_score=score)
    )

    assert record.status == "completed"
    assert record.step_result_status == result
    assert record.exercise_criteria_version_id == 301
    assert record.step_session_id == str(SESSION_ID)
    assert record.step_score == score


def test_rejects_unknown_step_result_status() -> None:
    with pytest.raises(ValidationError):
        payload(step_result_status="UNKNOWN")


def test_multiple_steps_keep_the_same_client_session_id(db_session: Session) -> None:
    seed_side_kick(db_session)

    first = create_exercise_step_record(db_session, user_id=1, payload=payload())
    second = create_exercise_step_record(
        db_session,
        user_id=1,
        payload=payload(exercise_step_id=102, step_result_status="NON_PASS", step_score=79),
    )

    assert first.step_session_id == second.step_session_id == str(SESSION_ID)


def test_rejects_step_that_does_not_belong_to_exercise(db_session: Session) -> None:
    seed_side_kick(db_session)

    with pytest.raises(HTTPException, match="EXERCISE_STEP_NOT_FOUND"):
        create_exercise_step_record(
            db_session, user_id=1, payload=payload(exercise_step_id=201)
        )


def test_rejects_criteria_version_from_another_exercise(db_session: Session) -> None:
    seed_side_kick(db_session)

    with pytest.raises(HTTPException, match="EXERCISE_CRITERIA_VERSION_NOT_FOUND"):
        create_exercise_step_record(
            db_session,
            user_id=1,
            payload=payload(exercise_criteria_version_id=302),
        )


def test_rejects_mismatched_json_criteria_version(db_session: Session) -> None:
    seed_side_kick(db_session)

    with pytest.raises(HTTPException, match="CRITERIA_VERSION_MISMATCH"):
        create_exercise_step_record(
            db_session, user_id=1, payload=payload(criteria_version="2.0.0")
        )


def test_rejects_step_report_with_a_different_criteria_version(
    db_session: Session,
) -> None:
    seed_side_kick(db_session)

    with pytest.raises(
        HTTPException, match="STEP_REPORT_CRITERIA_VERSION_MISMATCH"
    ):
        create_exercise_step_record(
            db_session,
            user_id=1,
            payload=payload(step_report={"criteria_version": "2.0.0"}),
        )


def test_rejects_criteria_version_without_this_steps_rule(db_session: Session) -> None:
    ids = seed_side_kick(db_session)
    db_session.query(ExerciseStepCriteriaVersion).filter_by(
        exercise_step_id=ids["left"],
        exercise_criteria_version_id=ids["criteria"],
    ).delete()
    db_session.commit()

    with pytest.raises(HTTPException, match="EXERCISE_STEP_CRITERIA_VERSION_NOT_FOUND"):
        create_exercise_step_record(db_session, user_id=1, payload=payload())


def test_historical_record_keeps_its_criteria_version_after_new_version_exists(
    db_session: Session,
) -> None:
    seed_side_kick(db_session)
    record = create_exercise_step_record(db_session, user_id=1, payload=payload())
    db_session.add(
        ExerciseCriteriaVersion(
            id=303,
            exercise_id=10,
            evaluation_criteria={},
            criteria_version="2.0.0",
            schema_version=1,
            status="ACTIVE",
        )
    )
    db_session.commit()

    assert db_session.get(type(record), record.id).exercise_criteria_version_id == 301


def test_study_config_returns_active_database_criteria_version(db_session: Session) -> None:
    seed_side_kick(db_session)

    config = get_sidekick_study_config(SimpleNamespace(id=1), db_session)

    assert config.exercise_criteria_version_id == 301
    assert config.criteria_version == "1.0.0"
