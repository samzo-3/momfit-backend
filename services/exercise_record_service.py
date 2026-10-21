"""운동 기록 생성, 일시 정지, 재개, 완료 서비스."""
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from core.clock import KST, utc_now
from core.errors import AppError
from models.exercise import Exercise
from models.exercise_criteria_version import ExerciseCriteriaVersion
from models.exercise_record import ExerciseRecord
from services.exercise_record_score import calculate_set_score
from services.exercise_scoring_config import get_scoring_rule


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
        .where(
            ExerciseCriteriaVersion.exercise_id == exercise_id,
            ExerciseCriteriaVersion.status == "ACTIVE",
        )
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
        completed_sets=0,
        status="in_progress",
        started_at=utc_now(),
        is_completed=False,
    )
    db.add(record)
    return _save(db, record)


# 한 번에 조회할 수 있는 최대 기간(일). 월 단위 캘린더와 주간 카드가 쓴다.
MAX_LIST_DAYS = 62


def _kst_day_start_as_utc(day: date) -> datetime:
    """KST 하루의 시작 시각을 DB에 저장된 naive UTC로 바꾼다."""
    start = datetime.combine(day, time.min, tzinfo=KST)
    return start.astimezone(timezone.utc).replace(tzinfo=None)


def list_records(db: Session, user_id: int, start: date, end: date):
    """KST 기준 start~end(양 끝 포함) 날짜에 시작한 내 운동 기록을 시작 시각 순으로 돌려준다."""
    if end < start:
        raise AppError(422, "INVALID_DATE_RANGE", "시작일이 종료일보다 늦습니다.")
    if (end - start).days + 1 > MAX_LIST_DAYS:
        raise AppError(
            422,
            "DATE_RANGE_TOO_LONG",
            f"한 번에 {MAX_LIST_DAYS}일까지만 조회할 수 있습니다.",
        )
    return db.scalars(
        select(ExerciseRecord)
        .where(
            ExerciseRecord.user_id == user_id,
            ExerciseRecord.started_at >= _kst_day_start_as_utc(start),
            ExerciseRecord.started_at < _kst_day_start_as_utc(end + timedelta(days=1)),
        )
        .order_by(ExerciseRecord.started_at, ExerciseRecord.id)
    ).all()


def kst_date(moment: datetime) -> date:
    """DB의 naive UTC 시각이 한국 시간으로 어느 날짜인지 돌려준다."""
    return moment.replace(tzinfo=timezone.utc).astimezone(KST).date()


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
        if record.status != "in_progress":
            if not (record.status == "paused" and not complete):
                raise HTTPException(409, "EXERCISE_NOT_IN_PROGRESS")

        criteria = db.get(
            ExerciseCriteriaVersion, record.exercise_criteria_version_id
        )
        if criteria is None:
            raise HTTPException(409, "EXERCISE_CRITERIA_NOT_FOUND")

        try:
            rule = get_scoring_rule(record.exercise_id)
            new_score = calculate_set_score(
                completed_sets, rule.target_sets, rule.score_per_set
            )
        except ValueError:
            raise HTTPException(422, "INVALID_COMPLETED_SETS") from None

        if completed_sets < record.completed_sets:
            raise HTTPException(409, "COMPLETED_SETS_CANNOT_DECREASE")

        record.completed_sets = completed_sets
        record.total_score = new_score
        if complete:
            record.status = "completed"
            record.is_completed = True
            record.ended_at = utc_now()
        else:
            record.status = "paused"
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
        if record.status != "paused" or record.is_completed:
            raise HTTPException(409, "EXERCISE_NOT_PAUSED")
        record.status = "in_progress"
        return _save(db, record)
    except Exception:
        db.rollback()
        raise
