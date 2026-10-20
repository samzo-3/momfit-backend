"""음성 코칭 조회 응답 및 데이터 검증 스키마."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


VoiceCategory = Literal["TRACKING", "EXERCISE", "STUDY"]


class VoiceCueBase(BaseModel):
    """음성 안내 공통 데이터."""

    model_config = ConfigDict(extra="forbid")

    exercise_id: int | None = Field(default=None, gt=0)
    exercise_step_id: int | None = Field(default=None, gt=0)

    category: VoiceCategory

    event_code: str | None = Field(default=None, max_length=50)
    audio_url: str = Field(min_length=1, max_length=500)

    is_active: bool = True
    message: str | None = None

    @model_validator(mode="after")
    def validate_scope(self) -> "VoiceCueBase":
        """카테고리별 운동 및 STEP 연결 규칙 검사."""

        if self.exercise_step_id is not None and self.exercise_id is None:
            raise ValueError(
                "exercise_step_id가 있으면 exercise_id도 필요합니다."
            )

        if self.category == "TRACKING":
            if self.exercise_id is not None or self.exercise_step_id is not None:
                raise ValueError(
                    "TRACKING 음성에는 운동 및 STEP ID를 지정할 수 없습니다."
                )

        if self.category == "EXERCISE":
            if self.exercise_step_id is not None:
                raise ValueError(
                    "EXERCISE 음성에는 STEP ID를 지정할 수 없습니다."
                )

        return self


class VoiceCueResponse(VoiceCueBase):
    """GET 음성 코칭 API의 개별 음성 응답."""

    model_config = ConfigDict(from_attributes=True, extra="forbid")

    id: int

    created_at: datetime
    modified_at: datetime
