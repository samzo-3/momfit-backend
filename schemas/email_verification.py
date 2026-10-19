"""이메일 인증 요청·응답 스키마."""

from typing import Literal

from pydantic import BaseModel, Field, field_validator

from schemas.validators import normalize_email

Purpose = Literal["signup", "password_reset"]


class SendCodeRequest(BaseModel):
    """인증 코드 발송 요청."""

    email: str = Field(max_length=255)
    purpose: Purpose

    @field_validator("email")
    @classmethod
    def _normalize_email(cls, value: str) -> str:
        return normalize_email(value)


class VerifyCodeRequest(BaseModel):
    """인증 코드 검증 요청."""

    email: str = Field(max_length=255)
    code: str = Field(pattern=r"^\d{6}$")
    purpose: Purpose

    @field_validator("email")
    @classmethod
    def _normalize_email(cls, value: str) -> str:
        return normalize_email(value)


class VerifyCodeResponse(BaseModel):
    """코드 검증 성공 응답. 가입·비밀번호 재설정 요청에 이 토큰을 함께 보낸다."""

    email_verification_token: str
    expires_in: int
