"""에이전트 스텝 피드백 모델. 팀 최종 ERD의 agent_step_feedback 테이블이다.

에이전트가 쓰는 테이블은 agent_step_feedback, agent_daily_feedback, daily_feedback_sources 셋이다.
팀 테이블은 읽기만 한다.
"""

from sqlalchemy import BigInteger, ForeignKey, Text
from sqlalchemy.orm import Mapped, mapped_column

from db.base import Base
from db.types import BigIntId
from models.timestamp_mixin import CreatedAtMixin

# FK가 가리키는 팀 테이블이 create_all에 늘 함께 잡히도록 팀 모델을 불러온다.
# (scripts/agent/run_scenarios.py처럼 main.py를 거치지 않고 models만 import하는 곳이 있다)
from models.exercise import Exercise  # noqa: F401
from models.exercise_step import ExerciseStep  # noqa: F401
from models.exercise_step_record import ExerciseStepRecord  # noqa: F401


class AgentStepFeedback(CreatedAtMixin, Base):
    """스텝 하나의 '오늘 메모'. 사용자에게 바로 보여 주지 않고, 일일 리포트를 쓸 때 참고한다.

    메모를 다시 쓰면 새 행이 쌓이고, 같은 스텝의 가장 최근 행이 현재 메모다.
    """

    __tablename__ = "agent_step_feedback"

    id: Mapped[int] = mapped_column(BigIntId, primary_key=True, autoincrement=True)
    # 팀의 탈퇴 삭제(30일 유예 후 users 행 삭제)가 이 테이블 때문에 막히지 않게 하고,
    # 탈퇴한 사람의 기록도 함께 지워지도록 CASCADE를 둔다.
    user_id: Mapped[int] = mapped_column(
        BigIntId, ForeignKey("users.id", ondelete="CASCADE")
    )
    # 그날 그 스텝의 '마지막 시도' 기록 번호. 메모가 어느 시도까지 반영했는지 알려 주는 표시이고,
    # 메모가 어느 스텝·어느 날의 것인지도 이 기록으로 안다.
    # 팀이 스텝 기록을 지울 때 이 테이블 때문에 막히지 않게 CASCADE로 함께 지운다.
    exercise_step_records_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("exercise_step_records.id", ondelete="CASCADE")
    )
    step_summary: Mapped[str | None] = mapped_column(Text)
