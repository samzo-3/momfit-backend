"""운동 기록 생성, 일시 정지, 재개, 완료 서비스."""
from decimal import Decimal

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from core.clock import utc_now
from models.exercise import Exercise
from models.exercise_criteria_version import ExerciseCriteriaVersion
from models.exercise_record import ExerciseRecord
from services.exercise_record_score import calculate_set_score


def _save(db: Session, record: ExerciseRecord) -> ExerciseRecord:
    try:
        db.commit()
        db.refresh(record)
    except Exception:
        db.rollback()
        raise
    return record


def _owned_record(db: Session, user_id: int, record_id: int, *, lock=False):
    query = select(ExerciseRecord).where(
        ExerciseRecord.id == record_id,
        ExerciseRecord.user_id == user_id,
    )
    if lock:
        query = query.with_for_update()
    record = db.scalar(query)
    if record is None:
        raise HTTPException(404, "EXERCISE_RECORD_NOT_FOUND")
    return record


def create_record(db: Session, user_id: int, exercise_id: int):
    exercise = db.get(Exercise, exercise_id)
    if exercise is None:
        raise HTTPException(404, "EXERCISE_NOT_FOUND")

    criteria = db.scalar(
        select(ExerciseCriteriaVersion)
        .where(ExerciseCriteriaVersion.exercise_id == exercise_id)
        .order_by(ExerciseCriteriaVersion.id.desc())
        .limit(1)
    )
    if criteria is None:
        raise HTTPException(409, "EXERCISE_CRITERIA_NOT_CONFIGURED")

    record = ExerciseRecord(
        user_id=user_id,
        exercise_id=exercise_id,
        exercise_criteria_version_id=criteria.id,
        total_score=Decimal("0.00"),
        status="IN_PROGRESS",
        is_completed=False,
    )
    db.add(record)
    return _save(db, record)


def get_record(db: Session, user_id: int, record_id: int):
    return _owned_record(db, user_id, record_id)


def _set_progress(
    db: Session,
    user_id: int,
    record_id: int,
    completed_sets: int,
    *,
    complete: bool,
):
    try:
        record = _owned_record(db, user_id, record_id, lock=True)
        if record.is_completed:
            raise HTTPException(409, "EXERCISE_ALREADY_COMPLETED")
        if record.status != "IN_PROGRESS":
            if not (record.status == "PAUSED" and not complete):
                raise HTTPException(409, "EXERCISE_NOT_IN_PROGRESS")

        criteria = db.get(
            ExerciseCriteriaVersion, record.exercise_criteria_version_id
        )
        if criteria is None:
            raise HTTPException(409, "EXERCISE_CRITERIA_NOT_FOUND")

        try:
            new_score = calculate_set_score(
                completed_sets, criteria.target_sets, criteria.score_per_set
            )
        except ValueError:
            raise HTTPException(422, "INVALID_COMPLETED_SETS") from None

        if new_score < record.total_score:
            raise HTTPException(409, "COMPLETED_SETS_CANNOT_DECREASE")

        record.total_score = new_score
        if complete:
            record.status = "COMPLETED"
            record.is_completed = True
            record.ended_at = utc_now()
        else:
            record.status = "PAUSED"
        return _save(db, record)
    except Exception:
        db.rollback()
        raise


def pause_record(db: Session, user_id: int, record_id: int, completed_sets: int):
    return _set_progress(
        db, user_id, record_id, completed_sets, complete=False
    )


def complete_record(db: Session, user_id: int, record_id: int, completed_sets: int):
    return _set_progress(
        db, user_id, record_id, completed_sets, complete=True
    )


def resume_record(db: Session, user_id: int, record_id: int):
    try:
        record = _owned_record(db, user_id, record_id, lock=True)
        if record.status != "PAUSED" or record.is_completed:
            raise HTTPException(409, "EXERCISE_NOT_PAUSED")
        record.status = "IN_PROGRESS"
        return _save(db, record)
    except Exception:
        db.rollback()
        raise
