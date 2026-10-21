"""STUDY STEP 수행 기록 저장 서비스."""

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from models.exercise import Exercise
from models.exercise_step import ExerciseStep
from models.exercise_step_record import ExerciseStepRecord
from schemas.exercise_step_record import ExerciseStepRecordCreate


def create_exercise_step_record(
    db: Session,
    *,
    user_id: int,
    payload: ExerciseStepRecordCreate,
) -> ExerciseStepRecord:

    exercise = db.get(Exercise, payload.exercise_id)

    if exercise is None:
        raise HTTPException(
            status_code=404,
            detail="EXERCISE_NOT_FOUND",
        )

    step = db.scalar(
        select(ExerciseStep).where(
            ExerciseStep.id == payload.exercise_step_id,
            ExerciseStep.exercise_id == payload.exercise_id,
        )
    )

    if step is None:
        raise HTTPException(
            status_code=404,
            detail="EXERCISE_STEP_NOT_FOUND",
        )

    record = ExerciseStepRecord(
        user_id=user_id,
        exercise_id=payload.exercise_id,
        exercise_step_id=payload.exercise_step_id,
        status=payload.status,
        step_score=payload.step_score,
        step_report=payload.step_report,
    )

    db.add(record)

    try:
        db.commit()
        db.refresh(record)
    except Exception:
        db.rollback()
        raise

    return record
