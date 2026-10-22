"""일별 방문 기록 모델. 로그인한 사용자가 그날 접속했는지만 남긴다."""

from datetime import date

from sqlalchemy import Date, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column

from db.base import Base
from db.types import BigIntId


class DailyVisit(Base):
    """사용자당 하루 한 행. 날짜는 Asia/Seoul 기준이다.

    로그인·토큰 갱신(앱을 열 때 세션 복구)으로 기록되며, 방문자수와 DAU/WAU/MAU 집계에 쓴다.
    """

    __tablename__ = "daily_visits"

    visit_date: Mapped[date] = mapped_column(Date, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        BigIntId, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
