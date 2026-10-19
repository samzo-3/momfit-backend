"""사용자 응답 스키마."""

from datetime import date
from typing import Literal

from pydantic import BaseModel


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
