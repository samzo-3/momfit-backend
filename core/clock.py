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
