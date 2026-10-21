"""일반 운동 기록 요청 및 응답."""
from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class ExerciseRecordCreate(BaseModel):
    exercise_id: int = Field(gt=0)


class ExerciseRecordProgress(BaseModel):
    completed_sets: int = Field(ge=0)


class ExerciseRecordResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    exercise_id: int
    exercise_criteria_version_id: int
    total_score: Decimal
    status: Literal["IN_PROGRESS", "PAUSED", "COMPLETED"]
    started_at: datetime
    ended_at: datetime | None
    is_completed: bool
    created_at: datetime
    modified_at: datetime
