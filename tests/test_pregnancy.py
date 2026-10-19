from datetime import date, timedelta

import pytest

from core.errors import AppError
from services.pregnancy import calculate_pregnancy_week, validate_due_date

TODAY = date(2026, 10, 19)


@pytest.mark.parametrize(
    ("days_until_due", "expected"),
    [
        (280, 0),  # 임신 0일 → 0주
        (273, 1),
        (84, 28),  # 196일 → 28주 0일
        (81, 28),  # 28주 3일
        (7, 39),  # 39주 0일
        (1, 39),  # 39주 6일
        (0, 40),  # 예정일 당일
        (-1, 40),  # 예정일 다음 날 (40주 1일)
        (-14, 42),  # 42주 0일
        (-100, 42),  # 42주 초과는 42로 고정
        (281, None),  # 임신 일수가 음수
    ],
)
def test_임신_주차_경계값(days_until_due: int, expected: int | None) -> None:
    due_date = TODAY + timedelta(days=days_until_due)

    assert calculate_pregnancy_week(due_date, TODAY) == expected


def test_예정일이_없으면_None() -> None:
    assert calculate_pregnancy_week(None, TODAY) is None


def test_예정일은_오늘부터_280일_이내를_허용한다() -> None:
    validate_due_date(TODAY, TODAY)
    validate_due_date(TODAY + timedelta(days=280), TODAY)


@pytest.mark.parametrize("offset", [-1, 281])
def test_범위_밖_예정일은_검증_오류(offset: int) -> None:
    with pytest.raises(AppError) as exc_info:
        validate_due_date(TODAY + timedelta(days=offset), TODAY)

    assert exc_info.value.status_code == 422
    assert "due_date" in (exc_info.value.fields or {})
