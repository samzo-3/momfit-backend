"""사용자 프로필 조회·수정, 회원 탈퇴 비즈니스 로직."""

from datetime import date

from sqlalchemy.orm import Session

from core.clock import today_kst
from models.user import User
from repositories import (
    email_verification_repository,
    refresh_token_repository,
    user_repository,
)
from schemas.user import UpdateProfileRequest, UserResponse
from services.pregnancy import calculate_pregnancy_week, validate_due_date


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


def update_profile(
    db: Session,
    user: User,
    request: UpdateProfileRequest,
    today: date | None = None,
) -> UserResponse:
    """보낸 필드만 수정한다. 출산 예정일은 가입할 때와 같은 범위 검증을 받는다."""
    today = today or today_kst()
    if "due_date" in request.model_fields_set:
        assert request.due_date is not None  # 요청 검증에서 null은 이미 걸러졌다.
        validate_due_date(request.due_date, today)

    for name in request.model_fields_set:
        setattr(user, name, getattr(request, name))
    db.commit()
    db.refresh(user)
    return to_user_response(user, today)


def delete_account(db: Session, user: User) -> None:
    """회원을 탈퇴시킨다. 로그인 수단, refresh 토큰, 이메일 인증 기록을 함께 삭제한다."""
    refresh_token_repository.delete_all_for_user(db, user.id)
    if user.email:
        email_verification_repository.delete_by_email(db, user.email)
    user_repository.delete(db, user)
    db.commit()
