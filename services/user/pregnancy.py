"""출산 예정일 기반 임신 주차 계산과 검증."""

from datetime import date, timedelta

from core.errors import AppError

PREGNANCY_DAYS = 280  # 40주
MAX_PREGNANCY_WEEK = 42


def calculate_pregnancy_week(due_date: date | None, today: date) -> int | None:
    """출산 예정일로 임신 주차를 계산한다.

    임신 일수가 음수이면 None, 42주를 넘으면 42로 고정한다.
    """
    if due_date is None:
        return None
    pregnancy_days = PREGNANCY_DAYS - (due_date - today).days
    if pregnancy_days < 0:
        return None
    return min(pregnancy_days // 7, MAX_PREGNANCY_WEEK)


def validate_due_date(due_date: date, today: date) -> None:
    """출산 예정일이 오늘부터 280일 이내인지 검증한다."""
    if not today <= due_date <= today + timedelta(days=PREGNANCY_DAYS):
        raise AppError(
            422,
            "VALIDATION_ERROR",
            "요청 값이 올바르지 않습니다.",
            {"due_date": "출산 예정일은 오늘부터 280일 이내여야 합니다."},
        )
