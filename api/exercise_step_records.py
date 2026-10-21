"""자세히 배우기 STEP 수행 결과 저장 API."""

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from api.deps import get_onboarded_user
from db.session import get_db
from models.user import User
from schemas.exercise_step_record import (
    ExerciseStepRecordCreate,
    ExerciseStepRecordResponse,
)
from services.exercise_step_record_service import (
    create_exercise_step_record,
)


router = APIRouter(
    prefix="/api/exercise-step-records",
    tags=["exercise-step-records"],
)


@router.post(
    "",
    response_model=ExerciseStepRecordResponse,
    status_code=status.HTTP_201_CREATED,
)
def save_exercise_step_record(
    payload: ExerciseStepRecordCreate,
    user: User = Depends(get_onboarded_user),
    db: Session = Depends(get_db),
) -> ExerciseStepRecordResponse:
    record = create_exercise_step_record(
        db,
        user_id=user.id,
        payload=payload,
    )
    return ExerciseStepRecordResponse.model_validate(record)
