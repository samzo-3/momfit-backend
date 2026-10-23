"""기존 Side Kick 전용 API와 별개인 범용 운동 카탈로그 API."""

from fastapi import APIRouter, Depends, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from api.deps import get_onboarded_user
from db.session import get_db
from models.exercise import Exercise
from models.user import User
from schemas.exercise_catalog import (
    ExerciseCriteriaResponse,
    ExerciseStepResponse,
    ExerciseSummary,
    StepSessionStartResponse,
)
from services.pose_coaching.exercise_catalog_service import (
    get_active_criteria,
    get_criteria_version,
    get_exercise,
    get_step,
    list_steps,
    start_step_session,
)


router = APIRouter(prefix="/api", tags=["exercises"])


@router.get("/exercises", response_model=list[ExerciseSummary])
def list_exercises(
    user: User = Depends(get_onboarded_user), db: Session = Depends(get_db)
) -> list[Exercise]:
    _ = user
    return db.scalars(select(Exercise).order_by(Exercise.id)).all()


@router.get("/exercises/{exercise_id}", response_model=ExerciseSummary)
def exercise_detail(
    exercise_id: int,
    user: User = Depends(get_onboarded_user),
    db: Session = Depends(get_db),
) -> Exercise:
    _ = user
    return get_exercise(db, exercise_id)


@router.get("/exercises/{exercise_id}/steps", response_model=list[ExerciseStepResponse])
def exercise_steps(
    exercise_id: int,
    user: User = Depends(get_onboarded_user),
    db: Session = Depends(get_db),
):
    _ = user
    return list_steps(db, exercise_id)


@router.get("/exercise-steps/{step_id}", response_model=ExerciseStepResponse)
def step_detail(
    step_id: int,
    user: User = Depends(get_onboarded_user),
    db: Session = Depends(get_db),
):
    _ = user
    return get_step(db, step_id)


@router.get("/exercises/{exercise_id}/criteria/active", response_model=ExerciseCriteriaResponse)
def active_criteria(
    exercise_id: int,
    user: User = Depends(get_onboarded_user),
    db: Session = Depends(get_db),
) -> ExerciseCriteriaResponse:
    _ = user
    return get_active_criteria(db, exercise_id)


@router.get("/exercises/{exercise_id}/criteria/{version_id}", response_model=ExerciseCriteriaResponse)
def criteria_version(
    exercise_id: int,
    version_id: int,
    user: User = Depends(get_onboarded_user),
    db: Session = Depends(get_db),
) -> ExerciseCriteriaResponse:
    _ = user
    return get_criteria_version(db, exercise_id, version_id)


@router.post(
    "/exercise-steps/{step_id}/step-sessions",
    response_model=StepSessionStartResponse,
    status_code=status.HTTP_201_CREATED,
)
def begin_step_session(
    step_id: int,
    user: User = Depends(get_onboarded_user),
    db: Session = Depends(get_db),
) -> StepSessionStartResponse:
    _ = user
    exercise_id, step_session_id = start_step_session(db, step_id)
    return StepSessionStartResponse(
        exercise_id=exercise_id,
        exercise_step_id=step_id,
        step_session_id=step_session_id,
    )
