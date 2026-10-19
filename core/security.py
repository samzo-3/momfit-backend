"""비밀번호 해시, JWT 발급·검증, refresh 토큰 생성."""

import hashlib
import secrets
from datetime import timedelta

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError

from core.clock import utc_now
from core.config import settings
from core.errors import AppError

ACCESS_TOKEN_TYPE = "access"
EMAIL_TOKEN_TYPE = "email_verification"
EMAIL_TOKEN_EXPIRE_SECONDS = 30 * 60

_password_hasher = PasswordHasher()
# 존재하지 않는 아이디로 로그인할 때도 해시 검증 시간을 맞추기 위한 더미 해시
_DUMMY_HASH = _password_hasher.hash("momfit-dummy-password")


def hash_password(password: str) -> str:
    """비밀번호를 argon2로 해시한다."""
    return _password_hasher.hash(password)


def verify_password(password: str, password_hash: str | None) -> bool:
    """비밀번호가 해시와 일치하는지 확인한다. 해시가 없으면 더미 해시로 시간만 소비한다."""
    try:
        return _password_hasher.verify(password_hash or _DUMMY_HASH, password) and bool(
            password_hash
        )
    except (VerificationError, InvalidHashError):
        return False


def create_access_token(user_id: int, expires_delta: timedelta | None = None) -> str:
    """사용자 access JWT를 발급한다."""
    delta = expires_delta or timedelta(minutes=settings.access_token_expire_minutes)
    payload = {
        "sub": str(user_id),
        "type": ACCESS_TOKEN_TYPE,
        "iat": utc_now(),
        "exp": utc_now() + delta,
    }
    return jwt.encode(
        payload, settings.require_jwt_secret(), algorithm=settings.jwt_algorithm
    )


def decode_access_token(token: str) -> int:
    """access JWT를 검증하고 사용자 id를 반환한다."""
    try:
        payload = jwt.decode(
            token,
            settings.require_jwt_secret(),
            algorithms=[settings.jwt_algorithm],
            options={"require": ["exp", "sub"]},
        )
    except jwt.ExpiredSignatureError:
        raise AppError(401, "TOKEN_EXPIRED", "토큰이 만료되었습니다.") from None
    except jwt.InvalidTokenError:
        raise AppError(401, "UNAUTHORIZED", "인증이 필요합니다.") from None
    if payload.get("type") != ACCESS_TOKEN_TYPE:
        raise AppError(401, "UNAUTHORIZED", "인증이 필요합니다.")
    try:
        return int(payload["sub"])
    except ValueError:
        raise AppError(401, "UNAUTHORIZED", "인증이 필요합니다.") from None


def create_email_verification_token(email: str, purpose: str) -> str:
    """이메일 인증 완료를 증명하는 JWT를 발급한다."""
    payload = {
        "type": EMAIL_TOKEN_TYPE,
        "email": email,
        "purpose": purpose,
        "exp": utc_now() + timedelta(seconds=EMAIL_TOKEN_EXPIRE_SECONDS),
    }
    return jwt.encode(
        payload, settings.require_jwt_secret(), algorithm=settings.jwt_algorithm
    )


def verify_email_verification_token(token: str, email: str, purpose: str) -> None:
    """이메일 인증 토큰이 유효하고 이메일·용도가 일치하는지 검증한다."""
    invalid = AppError(
        400, "EMAIL_TOKEN_INVALID", "이메일 인증이 유효하지 않습니다. 다시 진행해 주세요."
    )
    try:
        payload = jwt.decode(
            token,
            settings.require_jwt_secret(),
            algorithms=[settings.jwt_algorithm],
            options={"require": ["exp"]},
        )
    except jwt.InvalidTokenError:
        raise invalid from None
    if (
        payload.get("type") != EMAIL_TOKEN_TYPE
        or payload.get("email") != email
        or payload.get("purpose") != purpose
    ):
        raise invalid


def generate_refresh_token() -> str:
    """추측할 수 없는 refresh 토큰 원문을 생성한다."""
    return secrets.token_urlsafe(48)


def hash_refresh_token(token: str) -> str:
    """refresh 토큰을 DB 저장용 SHA-256 해시로 변환한다."""
    return hashlib.sha256(token.encode()).hexdigest()
