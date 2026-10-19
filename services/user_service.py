"""사용자 프로필 조회 비즈니스 로직."""

from datetime import date

from core.clock import today_kst
from models.user import User
from schemas.user import UserResponse
from services.pregnancy import calculate_pregnancy_week


def to_user_response(user: User, today: date | None = None) -> UserResponse:
    """User 모델을 응답 스키마로 변환한다. 임신 주차는 예정일에서 계산한다."""
    identity = user.identities[0] if user.identities else None
    return UserResponse(
        id=user.id,
        provider=identity.provider if identity else "local",
        login_id=identity.login_id if identity else None,
        nickname=user.nickname,
        email=user.email,
        due_date=user.due_date,
        pregnancy_week=calculate_pregnancy_week(user.due_date, today or today_kst()),
        exercise_level=user.exercise_level,
        onboarding_completed=user.onboarding_completed,
    )
