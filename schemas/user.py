"""사용자 응답 스키마."""

from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from schemas.auth import Consents


class UserResponse(BaseModel):
    """GET /users/me 응답."""

    id: int
    provider: Literal["local", "kakao"]
    login_id: str | None
    nickname: str
    email: str | None
    due_date: date | None
    pregnancy_week: int | None
    exercise_level: Literal["low", "medium", "high"] | None
    onboarding_completed: bool


class UpdateProfileRequest(BaseModel):
    """PATCH /users/me 요청. 바꿀 필드만 보낸다. 이메일·아이디 등은 바꿀 수 없다."""

    model_config = ConfigDict(extra="forbid")

    nickname: str | None = Field(default=None, max_length=20)
    due_date: date | None = None
    exercise_level: Literal["low", "medium", "high"] | None = None

    @field_validator("nickname")
    @classmethod
    def _strip_nickname(cls, value: str | None) -> str | None:
        if value is None:
            return value
        value = value.strip()
        if not value:
            raise ValueError("닉네임을 입력해 주세요.")
        return value

    @model_validator(mode="after")
    def _require_provided_values(self) -> "UpdateProfileRequest":
        if not self.model_fields_set:
            raise ValueError("바꿀 항목을 하나 이상 보내야 합니다.")
        # 보내지 않은 필드는 None이므로, 명시적으로 null을 보낸 경우만 걸러낸다.
        for name in self.model_fields_set:
            if getattr(self, name) is None:
                raise ValueError(f"{name}은(는) null로 바꿀 수 없습니다.")
        return self


class OnboardingRequest(BaseModel):
    """POST /users/me/onboarding 요청. 카카오로 처음 가입한 사용자가 동의와 초기 프로필을 제출한다."""

    model_config = ConfigDict(extra="forbid")

    nickname: str = Field(max_length=20)
    due_date: date
    exercise_level: Literal["low", "medium", "high"]
    consents: Consents

    @field_validator("nickname")
    @classmethod
    def _strip_nickname(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("닉네임을 입력해 주세요.")
        return value
