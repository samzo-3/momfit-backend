"""자세히 배우기 STEP 수행 기록 API 스키마."""

from datetime import datetime
from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


StepStatus = Literal["PASS", "NON_PASS", "NOT_EVALUATED"]


class ExerciseStepRecordCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    exercise_id: int = Field(gt=0)
    exercise_step_id: int = Field(gt=0)
    status: StepStatus
    step_score: Decimal | None = Field(default=None, ge=0, le=100)
    step_report: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_result(self):
        if self.status == "PASS":
            if self.step_score is None or self.step_score < 80:
                raise ValueError("PASS에는 80점 이상의 점수가 필요합니다.")

        if self.status == "NOT_EVALUATED" and self.step_score is not None:
            raise ValueError("NOT_EVALUATED에는 점수를 저장할 수 없습니다.")

        if self.status == "NON_PASS" and self.step_score is None:
            raise ValueError(
                "측정 점수가 없는 결과는 NOT_EVALUATED로 저장하세요."
            )

        return self


class ExerciseStepRecordResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    exercise_id: int
    exercise_step_id: int
    status: StepStatus
    step_score: Decimal | None
    step_report: dict[str, Any] | None
    created_at: datetime
    modified_at: datetime
