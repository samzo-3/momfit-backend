"""사용자 프로필 조회·수정, 온보딩 비즈니스 로직. (회원 탈퇴는 account_service)"""

from datetime import date, datetime

from sqlalchemy.orm import Session

from core.clock import today_kst, utc_now
from core.errors import AppError
from models.user import User
from schemas.user import OnboardingRequest, UpdateProfileRequest, UserResponse
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


def complete_onboarding(
    db: Session,
    user: User,
    request: OnboardingRequest,
    today: date | None = None,
    now: datetime | None = None,
) -> UserResponse:
    """카카오로 처음 가입한 사용자의 동의와 초기 프로필을 저장하고 온보딩을 마친다."""
    if user.onboarding_completed:
        raise AppError(
            409, "ONBOARDING_ALREADY_COMPLETED", "이미 온보딩을 마친 계정입니다."
        )
    today = today or today_kst()
    now = now or utc_now()
    validate_due_date(request.due_date, today)

    user.nickname = request.nickname
    user.due_date = request.due_date
    user.exercise_level = request.exercise_level
    user.terms_agreed_at = now
    user.health_data_agreed_at = now
    user.onboarding_completed = True
    db.commit()
    db.refresh(user)
    return to_user_response(user, today)
