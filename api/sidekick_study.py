"""Side Kick STUDY 운동 및 STEP ID 조회."""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from api.deps import get_onboarded_user
from db.session import get_db
from models.exercise import Exercise
from models.exercise_step import ExerciseStep
from models.user import User


router = APIRouter(
    prefix="/api/exercises/sidekick",
    tags=["sidekick-study"],
)


class StudyStepInfo(BaseModel):
    step_no: int
    exercise_step_id: int
    step_name: str


class SideKickStudyConfig(BaseModel):
    exercise_id: int
    exercise_name: str
    steps: list[StudyStepInfo]


@router.get("/study-config", response_model=SideKickStudyConfig)
def get_sidekick_study_config(
    user: User = Depends(get_onboarded_user),
    db: Session = Depends(get_db),
) -> SideKickStudyConfig:
    _ = user

    exercises = db.scalars(
        select(Exercise).where(
            Exercise.exercise_name == "Side Kick"
        )
    ).all()

    if len(exercises) != 1:
        raise HTTPException(
            status_code=409,
            detail="SIDEKICK_EXERCISE_NOT_CONFIGURED",
        )

    exercise = exercises[0]

    steps = db.scalars(
        select(ExerciseStep)
        .where(ExerciseStep.exercise_id == exercise.id)
        .order_by(ExerciseStep.step_order)
    ).all()

    if [step.step_order for step in steps] != [1, 2, 3, 4, 5]:
        raise HTTPException(
            status_code=409,
            detail="SIDEKICK_STEPS_NOT_CONFIGURED",
        )

    return SideKickStudyConfig(
        exercise_id=exercise.id,
        exercise_name=exercise.exercise_name,
        steps=[
            StudyStepInfo(
                step_no=step.step_order,
                exercise_step_id=step.id,
                step_name=step.step_name,
            )
            for step in steps
        ],
    )
