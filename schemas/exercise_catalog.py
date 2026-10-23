"""운동 카탈로그와 평가 기준 조회 계약."""

from typing import Any
from pydantic import BaseModel, ConfigDict


class ExerciseSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    exercise_name: str
    video_url: str
    description: str | None


class ExerciseStepResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    exercise_id: int
    step_order: int
    step_name: str
    clip_video_url: str
    step_description: str | None
    important: bool


class ExerciseCriteriaStepResponse(BaseModel):
    id: int
    exercise_step_id: int
    step_order: int
    step_name: str
    step_criteria_version: str
    evaluation_criteria: dict[str, Any]


class ExerciseCriteriaResponse(BaseModel):
    id: int
    exercise_id: int
    criteria_version: str
    schema_version: int
    status: str
    evaluation_criteria: dict[str, Any]
    steps: list[ExerciseCriteriaStepResponse]
