"""일일 피드백에 반영된 스텝 피드백. 팀 최종 ERD의 daily_feedback_sources 테이블이다."""

from sqlalchemy import ForeignKey
from sqlalchemy.orm import Mapped, mapped_column

from db.base import Base
from db.types import BigIntId
from models.agent.agent_daily_feedback import AgentDailyFeedback  # noqa: F401
from models.agent.agent_step_feedback import AgentStepFeedback  # noqa: F401


class DailyFeedbackSource(Base):
    """일일 리포트 한마디가 어떤 스텝 메모를 보고 썼는지 잇는 한 줄.

    LLM이 쓴 한마디만 잇는다. 숫자만으로 쓴 대체 문장은 스텝 메모를 반영하지 않았으므로 잇지 않는다.
    """

    __tablename__ = "daily_feedback_sources"

    id: Mapped[int] = mapped_column(BigIntId, primary_key=True, autoincrement=True)
    # 어느 쪽 행이 지워져도(탈퇴 삭제, 스텝 기록 삭제) 이 연결 때문에 막히지 않게 CASCADE로 함께 지운다.
    agent_daily_feedback_id: Mapped[int] = mapped_column(
        BigIntId, ForeignKey("agent_daily_feedback.id", ondelete="CASCADE")
    )
    agent_step_feedback_id: Mapped[int] = mapped_column(
        BigIntId, ForeignKey("agent_step_feedback.id", ondelete="CASCADE")
    )
