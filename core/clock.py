"""시간 관련 공통 유틸. DB에는 naive UTC, 임신 주차 계산에는 한국 날짜를 쓴다."""

from datetime import date, datetime, timedelta, timezone

# 한국은 DST가 없으므로 고정 오프셋으로 충분하다.
KST = timezone(timedelta(hours=9), "Asia/Seoul")


def utc_now() -> datetime:
    """DB 저장용 naive UTC 현재 시각을 반환한다."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def today_kst() -> date:
    """Asia/Seoul 기준 오늘 날짜를 반환한다."""
    return datetime.now(KST).date()


def kst_date(utc_naive: datetime) -> date:
    """DB에 저장하는 naive UTC 시각을 Asia/Seoul 기준 날짜로 바꾼다."""
    return utc_naive.replace(tzinfo=timezone.utc).astimezone(KST).date()


def kst_day_start_utc(day: date) -> datetime:
    """KST 기준 day의 00:00에 해당하는 naive UTC 시각. DB의 시각 컬럼과 비교할 때 쓴다."""
    return datetime(day.year, day.month, day.day, tzinfo=KST).astimezone(
        timezone.utc
    ).replace(tzinfo=None)
