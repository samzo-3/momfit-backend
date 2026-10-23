"""STUDY STEP 수행 기록 저장 서비스."""

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from models.exercise import Exercise
from models.exercise_criteria_version import ExerciseCriteriaVersion
from models.exercise_step import ExerciseStep
from models.exercise_step_criteria_version import ExerciseStepCriteriaVersion
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

    criteria_version = db.scalar(
        select(ExerciseCriteriaVersion).where(
            ExerciseCriteriaVersion.id == payload.exercise_criteria_version_id,
            ExerciseCriteriaVersion.exercise_id == payload.exercise_id,
        )
    )
    if criteria_version is None:
        raise HTTPException(
            status_code=404,
            detail="EXERCISE_CRITERIA_VERSION_NOT_FOUND",
        )

    if criteria_version.criteria_version != payload.criteria_version:
        raise HTTPException(
            status_code=422,
            detail="CRITERIA_VERSION_MISMATCH",
        )

    if payload.step_report.get("criteria_version") != payload.criteria_version:
        raise HTTPException(
            status_code=422,
            detail="STEP_REPORT_CRITERIA_VERSION_MISMATCH",
        )

    step_criteria_version = db.scalar(
        select(ExerciseStepCriteriaVersion).where(
            ExerciseStepCriteriaVersion.exercise_step_id == payload.exercise_step_id,
            ExerciseStepCriteriaVersion.exercise_criteria_version_id
            == payload.exercise_criteria_version_id,
        )
    )
    if step_criteria_version is None:
        raise HTTPException(
            status_code=409,
            detail="EXERCISE_STEP_CRITERIA_VERSION_NOT_FOUND",
        )

    record = ExerciseStepRecord(
        user_id=user_id,
        exercise_id=payload.exercise_id,
        exercise_step_id=payload.exercise_step_id,
        exercise_criteria_version_id=payload.exercise_criteria_version_id,
        step_session_id=str(payload.step_session_id),
        status="completed",
        step_result_status=payload.step_result_status,
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
