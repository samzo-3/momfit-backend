"""로컬 인증(가입, 로그인, 토큰 갱신, 로그아웃) 비즈니스 로직."""

import uuid
from dataclasses import dataclass
from datetime import date, datetime, timedelta

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from core.clock import today_kst, utc_now
from core.config import settings
from core.errors import AppError
from core.security import (
    create_access_token,
    generate_refresh_token,
    hash_password,
    hash_refresh_token,
    verify_email_verification_token,
    verify_password,
)
from models.auth_identity import LOCAL_PROVIDER, AuthIdentity
from models.refresh_token import RefreshToken
from models.user import STATUS_ACTIVE, User
from repositories import (
    auth_identity_repository,
    refresh_token_repository,
    user_repository,
)
from schemas.auth import LoginRequest, PasswordResetRequest, SignupRequest
from services.pregnancy import validate_due_date


class AccountWithdrawnError(Exception):
    """탈퇴 유예 중인 계정이 인증을 마쳤다. 호출한 쪽이 복구 안내로 이어 준다."""

    def __init__(self, user_id: int) -> None:
        super().__init__("탈퇴 처리된 계정입니다.")
        self.user_id = user_id


@dataclass(frozen=True)
class IssuedTokens:
    """발급된 토큰. refresh는 쿠키로, access는 본문으로 내려간다."""

    access_token: str
    refresh_token: str
    expires_in: int


def _refresh_invalid() -> AppError:
    return AppError(401, "REFRESH_INVALID", "다시 로그인해 주세요.")


def issue_tokens(
    db: Session, user_id: int, family_id: str, now: datetime
) -> IssuedTokens:
    refresh_token = generate_refresh_token()
    refresh_token_repository.add(
        db,
        RefreshToken(
            user_id=user_id,
            token_hash=hash_refresh_token(refresh_token),
            family_id=family_id,
            expires_at=now + timedelta(days=settings.refresh_token_expire_days),
        ),
    )
    return IssuedTokens(
        access_token=create_access_token(user_id),
        refresh_token=refresh_token,
        expires_in=settings.access_token_expire_minutes * 60,
    )


def is_login_id_available(db: Session, login_id: str) -> bool:
    """로컬 로그인 아이디가 사용 가능한지 확인한다. 대소문자는 구분하지 않는다."""
    return auth_identity_repository.get_local_by_login_id(db, login_id.lower()) is None


def signup(
    db: Session,
    request: SignupRequest,
    today: date | None = None,
    now: datetime | None = None,
) -> IssuedTokens:
    """이메일 인증을 마친 사용자를 로컬 계정으로 가입시키고 로그인 처리한다."""
    today = today or today_kst()
    now = now or utc_now()

    verify_email_verification_token(
        request.email_verification_token, request.email, "signup"
    )
    validate_due_date(request.due_date, today)

    if auth_identity_repository.get_local_by_login_id(db, request.login_id):
        raise AppError(409, "LOGIN_ID_EXISTS", "이미 사용 중인 아이디입니다.")
    if user_repository.get_by_email(db, request.email):
        raise AppError(409, "EMAIL_EXISTS", "이미 가입된 이메일입니다.")

    try:
        user = user_repository.add(
            db,
            User(
                nickname=request.nickname,
                email=request.email,
                due_date=request.due_date,
                exercise_level=request.exercise_level,
                onboarding_completed=True,
                terms_agreed_at=now,
                health_data_agreed_at=now,
            ),
        )
        auth_identity_repository.add(
            db,
            AuthIdentity(
                user_id=user.id,
                provider=LOCAL_PROVIDER,
                provider_user_id=request.login_id,
                login_id=request.login_id,
                password_hash=hash_password(request.password),
            ),
        )
        tokens = issue_tokens(db, user.id, str(uuid.uuid4()), now)
        db.commit()
    except IntegrityError:
        # 위의 중복 확인과 저장 사이에 같은 값으로 가입한 요청이 끼어든 경우
        db.rollback()
        raise AppError(409, "LOGIN_ID_EXISTS", "이미 사용 중이거나 가입된 정보입니다.") from None
    return tokens


def login(db: Session, request: LoginRequest, now: datetime | None = None) -> IssuedTokens:
    """아이디·비밀번호로 로그인한다."""
    now = now or utc_now()
    login_id = request.login_id.strip().lower()

    identity = auth_identity_repository.get_local_by_login_id(db, login_id)
    # 계정이 없어도 해시 검증을 수행해 응답 시간으로 존재 여부가 드러나지 않게 한다.
    password_ok = verify_password(
        request.password, identity.password_hash if identity else None
    )
    if not identity or not password_ok:
        raise AppError(
            401, "INVALID_CREDENTIALS", "아이디 또는 비밀번호가 올바르지 않습니다."
        )

    # 비밀번호가 맞아도 탈퇴 유예 중이면 로그인시키지 않고 복구 안내로 넘긴다.
    # (비밀번호 확인 뒤에 알려 주므로, 계정 존재 여부가 비밀번호 없이 드러나지 않는다)
    user = user_repository.get_by_id(db, identity.user_id)
    if user is not None and user.status != STATUS_ACTIVE:
        raise AccountWithdrawnError(user.id)

    tokens = issue_tokens(db, identity.user_id, str(uuid.uuid4()), now)
    db.commit()
    return tokens


def refresh(db: Session, refresh_token: str | None, now: datetime | None = None) -> IssuedTokens:
    """refresh 토큰을 교체(rotation)하고 새 access 토큰을 발급한다.

    이미 사용된 토큰이 다시 오면 탈취로 보고 같은 family를 모두 폐기한다.
    """
    now = now or utc_now()
    if not refresh_token:
        raise _refresh_invalid()

    stored = refresh_token_repository.get_by_hash_for_update(
        db, hash_refresh_token(refresh_token)
    )
    if stored is None:
        raise _refresh_invalid()
    if stored.revoked_at is not None:
        refresh_token_repository.revoke_family(db, stored.family_id, now)
        db.commit()
        raise _refresh_invalid()
    if stored.expires_at <= now:
        raise _refresh_invalid()

    user = user_repository.get_by_id(db, stored.user_id)
    if user is None or user.status != STATUS_ACTIVE:
        raise _refresh_invalid()

    stored.revoked_at = now
    tokens = issue_tokens(db, stored.user_id, stored.family_id, now)
    db.commit()
    return tokens


def logout(db: Session, refresh_token: str | None, now: datetime | None = None) -> None:
    """refresh 토큰이 속한 family를 폐기한다. 유효하지 않은 토큰이어도 오류로 보지 않는다."""
    if not refresh_token:
        return
    stored = refresh_token_repository.get_by_hash_for_update(
        db, hash_refresh_token(refresh_token)
    )
    if stored is not None:
        refresh_token_repository.revoke_family(db, stored.family_id, now or utc_now())
        db.commit()


def reset_password(
    db: Session, request: PasswordResetRequest, now: datetime | None = None
) -> None:
    """이메일 인증을 마친 사용자의 비밀번호를 바꾸고, 모든 기기의 로그인을 해제한다."""
    now = now or utc_now()
    verify_email_verification_token(
        request.email_verification_token, request.email, "password_reset"
    )
    user = user_repository.get_by_email(db, request.email)
    identity = (
        auth_identity_repository.get_local_by_user_id(db, user.id) if user else None
    )
    if identity is None:
        raise AppError(
            400, "EMAIL_TOKEN_INVALID", "이메일 인증이 유효하지 않습니다. 다시 진행해 주세요."
        )

    identity.password_hash = hash_password(request.new_password)
    refresh_token_repository.revoke_all_for_user(db, identity.user_id, now)
    db.commit()
