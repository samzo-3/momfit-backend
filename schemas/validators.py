"""여러 스키마가 공유하는 입력 검증."""

import re

_EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def normalize_email(value: str) -> str:
    """이메일을 공백 제거·소문자로 정규화하고 형식을 검증한다."""
    value = value.strip().lower()
    if not _EMAIL_PATTERN.match(value):
        raise ValueError("이메일 형식이 올바르지 않습니다.")
    return value


def validate_password(value: str) -> str:
    """비밀번호 규칙(8자 이상, 영문과 숫자 포함)을 검증한다."""
    if len(value) < 8 or not re.search(r"[A-Za-z]", value) or not re.search(r"\d", value):
        raise ValueError("8자 이상, 영문과 숫자를 포함해야 합니다.")
    return value
