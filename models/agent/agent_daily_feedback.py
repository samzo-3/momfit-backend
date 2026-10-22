"""에이전트 일일 피드백 모델. 팀 최종 ERD의 agent_daily_feedback 테이블이다."""

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from core.clock import utc_now
from db.base import Base
from db.types import BigIntId

# 팀 최종 ERD의 today_summary 길이 (VARCHAR(255))
TODAY_SUMMARY_MAX_LENGTH = 255


class AgentDailyFeedback(Base):
    """사용자에게 보여 준 '오늘의 운동 리포트' 한마디.

    같은 날 다시 만들면 새 행이 쌓이고, 가장 최근 행이 그날의 리포트다.
    어떤 스텝 메모를 보고 썼는지는 daily_feedback_sources에 남긴다.
    """

    __tablename__ = "agent_daily_feedback"

    id: Mapped[int] = mapped_column(BigIntId, primary_key=True, autoincrement=True)
    # 팀의 탈퇴 삭제가 이 테이블 때문에 막히지 않게 CASCADE를 둔다. (agent_step_feedback과 같다)
    user_id: Mapped[int] = mapped_column(
        BigIntId, ForeignKey("users.id", ondelete="CASCADE")
    )
    # 한마디와 다음 집중 스텝 한 줄을 합친 문장. 서비스가 255자를 넘지 않게 맞춘다.
    today_summary: Mapped[str | None] = mapped_column(String(TODAY_SUMMARY_MAX_LENGTH))
    # KST 날짜의 00:00을 naive로 저장한다. 팀의 다른 시각 컬럼은 naive UTC지만, 이 컬럼은
    # '어느 날의 리포트인가'를 뜻하는 날짜라서 KST 자정으로 맞춘다.
    report_date: Mapped[datetime | None] = mapped_column(DateTime)
    # 저장 시각이 아니라 리포트가 숫자를 센 시각을 넣는다. (agent_feedback_repository.save_daily_report)
    created_at: Mapped[datetime | None] = mapped_column(DateTime, default=utc_now)
    modified_at: Mapped[datetime | None] = mapped_column(
        DateTime, default=utc_now, onupdate=utc_now
    )
