"""자세히 배우기 STEP 수행 기록 API 스키마."""

from datetime import datetime
from decimal import Decimal
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


StepResultStatus = Literal["PASS", "NON_PASS", "NOT_EVALUATED"]
StepRecordStatus = Literal["in_progress", "completed"]


class ExerciseStepRecordCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    exercise_id: int = Field(gt=0)
    exercise_step_id: int = Field(gt=0)
    exercise_criteria_version_id: int = Field(gt=0)
    criteria_version: str = Field(min_length=1, max_length=100)
    step_session_id: UUID
    step_result_status: StepResultStatus
    step_score: Decimal | None = Field(default=None, ge=0, le=100)
    step_report: dict[str, Any] = Field(default_factory=dict)

class ExerciseStepRecordResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    exercise_id: int
    exercise_step_id: int
    exercise_criteria_version_id: int
    step_session_id: UUID
    status: StepRecordStatus
    step_result_status: StepResultStatus
    step_score: Decimal | None
    step_report: dict[str, Any] | None
    created_at: datetime
    modified_at: datetime
