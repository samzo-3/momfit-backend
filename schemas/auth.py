"""인증 요청·응답 스키마."""

import re
from datetime import date
from typing import Literal

from pydantic import BaseModel, Field, ValidationInfo, field_validator

_EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class Consents(BaseModel):
    """약관·민감정보 수집 동의. 둘 다 true여야 한다."""

    terms: bool
    health_data: bool

    @field_validator("health_data")
    @classmethod
    def _require_all(cls, value: bool, info: ValidationInfo) -> bool:
        if not (value and info.data.get("terms")):
            raise ValueError("이용약관과 건강정보 수집에 모두 동의해야 합니다.")
        return value


class SignupRequest(BaseModel):
    """로컬 가입 요청."""

    login_id: str = Field(pattern=r"^[a-z0-9]{4,20}$")
    password: str = Field(max_length=128)
    nickname: str = Field(min_length=1, max_length=20)
    email: str = Field(max_length=255)
    email_verification_token: str
    due_date: date
    exercise_level: Literal["low", "medium", "high"]
    consents: Consents

    @field_validator("password")
    @classmethod
    def _check_password(cls, value: str) -> str:
        if (
            len(value) < 8
            or not re.search(r"[A-Za-z]", value)
            or not re.search(r"\d", value)
        ):
            raise ValueError("8자 이상, 영문과 숫자를 포함해야 합니다.")
        return value

    @field_validator("nickname")
    @classmethod
    def _strip_nickname(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("닉네임을 입력해 주세요.")
        return value

    @field_validator("email")
    @classmethod
    def _normalize_email(cls, value: str) -> str:
        value = value.strip().lower()
        if not _EMAIL_PATTERN.match(value):
            raise ValueError("이메일 형식이 올바르지 않습니다.")
        return value


class LoginRequest(BaseModel):
    """로컬 로그인 요청."""

    login_id: str = Field(min_length=1, max_length=50)
    password: str = Field(min_length=1, max_length=128)


class CheckLoginIdResponse(BaseModel):
    """아이디 중복 확인 응답."""

    available: bool


class TokenResponse(BaseModel):
    """access 토큰 응답. refresh 토큰은 쿠키로 내려간다."""

    access_token: str
    token_type: Literal["bearer"] = "bearer"
    expires_in: int
