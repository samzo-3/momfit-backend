from datetime import timedelta

import jwt
import pytest

from core import security
from core.config import settings
from core.errors import AppError


def test_비밀번호_해시는_원문과_다르고_검증된다() -> None:
    hashed = security.hash_password("password1")

    assert hashed != "password1"
    assert security.verify_password("password1", hashed) is True
    assert security.verify_password("wrong-pass1", hashed) is False


def test_해시가_없으면_항상_검증에_실패한다() -> None:
    assert security.verify_password("momfit-dummy-password", None) is False


def test_access_토큰_왕복() -> None:
    token = security.create_access_token(42)

    assert security.decode_access_token(token) == 42


def test_만료된_access_토큰은_TOKEN_EXPIRED() -> None:
    token = security.create_access_token(1, expires_delta=timedelta(seconds=-1))

    with pytest.raises(AppError) as exc_info:
        security.decode_access_token(token)

    assert exc_info.value.code == "TOKEN_EXPIRED"


def test_변조되거나_형식이_틀린_토큰은_UNAUTHORIZED() -> None:
    with pytest.raises(AppError) as exc_info:
        security.decode_access_token("not-a-jwt")

    assert exc_info.value.code == "UNAUTHORIZED"


def test_이메일_인증_토큰은_access_토큰으로_쓸_수_없다() -> None:
    token = security.create_email_verification_token("a@b.com", "signup")

    with pytest.raises(AppError) as exc_info:
        security.decode_access_token(token)

    assert exc_info.value.code == "UNAUTHORIZED"


def test_다른_서명_키로_만든_토큰은_거부한다() -> None:
    forged = jwt.encode(
        {"sub": "1", "type": "access", "exp": 9999999999},
        "other-signing-key-0123456789-0123456789",
        algorithm=settings.jwt_algorithm,
    )

    with pytest.raises(AppError):
        security.decode_access_token(forged)


def test_이메일_인증_토큰_검증() -> None:
    token = security.create_email_verification_token("a@b.com", "signup")

    security.verify_email_verification_token(token, "a@b.com", "signup")


@pytest.mark.parametrize(
    ("email", "purpose"), [("other@b.com", "signup"), ("a@b.com", "password_reset")]
)
def test_이메일이나_용도가_다르면_EMAIL_TOKEN_INVALID(email: str, purpose: str) -> None:
    token = security.create_email_verification_token("a@b.com", "signup")

    with pytest.raises(AppError) as exc_info:
        security.verify_email_verification_token(token, email, purpose)

    assert exc_info.value.code == "EMAIL_TOKEN_INVALID"


def test_refresh_토큰은_매번_다르고_해시는_결정적이다() -> None:
    first, second = security.generate_refresh_token(), security.generate_refresh_token()

    assert first != second
    assert security.hash_refresh_token(first) == security.hash_refresh_token(first)
    assert security.hash_refresh_token(first) != first
