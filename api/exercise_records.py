"""일반 운동 기록 API."""
from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from api.deps import get_onboarded_user
from db.session import get_db
from models.user import User
from schemas.exercise_record import (
    ExerciseRecordCreate,
    ExerciseRecordProgress,
    ExerciseRecordResponse,
)
from services.exercise_record_service import (
    complete_record,
    create_record,
    get_record,
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
