"""일반 운동 기록 API."""
from datetime import date

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from api.deps import get_onboarded_user
from db.session import get_db
from models.user import User
from schemas.exercise_record import (
    ExerciseRecordCreate,
    ExerciseRecordListResponse,
    ExerciseRecordProgress,
    ExerciseRecordResponse,
    ExerciseRecordSummary,
)
from services.pose_coaching.exercise_record_service import (
    complete_record,
    create_record,
    get_record,
    kst_date,
    list_records,
    pause_record,
    resume_record,
)

router = APIRouter(
    prefix="/api/exercise-records",
    tags=["exercise-records"],
)


@router.post(
    "",
    response_model=ExerciseRecordResponse,
    status_code=status.HTTP_201_CREATED,
)
def create(
    payload: ExerciseRecordCreate,
    user: User = Depends(get_onboarded_user),
    db: Session = Depends(get_db),
):
    return create_record(db, user.id, payload.exercise_id)


@router.get("", response_model=ExerciseRecordListResponse)
def list_(
    start: date = Query(alias="from", description="조회 시작일(KST, 포함)"),
    end: date = Query(alias="to", description="조회 종료일(KST, 포함)"),
    user: User = Depends(get_onboarded_user),
    db: Session = Depends(get_db),
):
    """캘린더용. 기간 안에 시작한 내 운동 기록을 날짜(KST)와 함께 돌려준다."""
    records = list_records(db, user.id, start, end)
    return ExerciseRecordListResponse(
        items=[
            ExerciseRecordSummary(
                id=r.id,
                exercise_id=r.exercise_id,
                status=r.status,
                is_completed=r.is_completed,
                date=kst_date(r.started_at),
                started_at=r.started_at,
                ended_at=r.ended_at,
            )
            for r in records
        ]
    )


@router.get("/{record_id}", response_model=ExerciseRecordResponse)
def get_one(
    record_id: int,
    user: User = Depends(get_onboarded_user),
    db: Session = Depends(get_db),
):
    return get_record(db, user.id, record_id)


@router.patch("/{record_id}/pause", response_model=ExerciseRecordResponse)
def pause(
    record_id: int,
    payload: ExerciseRecordProgress,
    user: User = Depends(get_onboarded_user),
    db: Session = Depends(get_db),
):
    return pause_record(db, user.id, record_id, payload.completed_sets)


@router.patch("/{record_id}/resume", response_model=ExerciseRecordResponse)
def resume(
    record_id: int,
    user: User = Depends(get_onboarded_user),
    db: Session = Depends(get_db),
):
    return resume_record(db, user.id, record_id)


@router.patch("/{record_id}/complete", response_model=ExerciseRecordResponse)
def complete(
    record_id: int,
    payload: ExerciseRecordProgress,
    user: User = Depends(get_onboarded_user),
    db: Session = Depends(get_db),
):
    return complete_record(db, user.id, record_id, payload.completed_sets)
