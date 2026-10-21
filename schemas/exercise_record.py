"""일반 운동 기록 요청 및 응답."""
from datetime import date, datetime
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
    completed_sets: int
    status: Literal["in_progress", "paused", "completed"]
    started_at: datetime
    ended_at: datetime | None
    is_completed: bool
    created_at: datetime
    modified_at: datetime


class ExerciseRecordSummary(BaseModel):
    """캘린더용 요약. date는 started_at을 한국 시간(KST)으로 본 날짜다."""

    id: int
    exercise_id: int
    status: Literal["in_progress", "paused", "completed"]
    is_completed: bool
    date: date
    started_at: datetime
    ended_at: datetime | None


class ExerciseRecordListResponse(BaseModel):
    items: list[ExerciseRecordSummary]
