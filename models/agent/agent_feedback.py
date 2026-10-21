"""에이전트 피드백 모델. 팀 최종 ERD의 agent_feedback 테이블이다.

에이전트가 쓰는 유일한 테이블이다. 팀 테이블은 읽기만 한다.
"""

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from core.clock import utc_now
from db.base import Base

# FK가 가리키는 팀 테이블이 create_all에 늘 함께 잡히도록 팀 모델을 불러온다.
# (scripts/agent/run_scenarios.py처럼 main.py를 거치지 않고 models만 import하는 곳이 있다)
from models.exercise import Exercise  # noqa: F401
from models.exercise_step import ExerciseStep  # noqa: F401
from models.exercise_step_record import ExerciseStepRecord  # noqa: F401

FEEDBACK_TYPE_DAILY = "DAILY"
FEEDBACK_TYPE_STEP = "STEP"


class AgentFeedback(Base):
    """에이전트가 쓴 피드백 한 줄.

    DAILY: 사용자에게 보여 준 '오늘의 운동 리포트' 한마디. 같은 날 다시 요청하면 새 행이 쌓이고,
           가장 최근 행이 그날의 리포트다.
    STEP:  스텝 하나의 '오늘 메모'. 사용자에게 바로 보여 주지 않고, DAILY를 쓸 때 참고한다.
    """

    __tablename__ = "agent_feedback"

    id: Mapped[int] = mapped_column(primary_key=True)
    # 팀의 탈퇴 삭제(30일 유예 후 users 행 삭제)가 이 테이블 때문에 막히지 않게 하고,
    # 탈퇴한 사람의 기록도 함께 지워지도록 CASCADE를 둔다.
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    # STEP 행에는 그날 그 스텝의 '마지막 시도' 기록 번호를 넣는다. 메모가 어느 시도까지
    # 반영했는지 알려 주는 표시다. DAILY 행은 특정 스텝 기록이 없어서 비어 있다.
    # (팀 최종 ERD는 NOT NULL이라 NULL 허용을 팀에 확인 중이다.)
    # 팀이 스텝 기록을 지울 때 이 테이블 때문에 막히지 않게 CASCADE로 함께 지운다.
    exercise_step_records_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("exercise_step_records.id", ondelete="CASCADE")
    )
    feedback_type: Mapped[str] = mapped_column(String(20), index=True)
    today_summary: Mapped[str | None] = mapped_column(Text)
    step_summary: Mapped[str | None] = mapped_column(Text)
    # KST 날짜의 00:00을 naive로 저장한다. 팀의 다른 시각 컬럼은 naive UTC지만, 이 컬럼은
    # '어느 날의 기록인가'를 뜻하는 날짜라서 KST 자정으로 맞춘다.
    # DAILY는 리포트 날짜, STEP은 그 메모가 요약한 시도들의 날짜다. 날짜로 바로 찾을 수 있게
    # STEP에도 반드시 채운다.
    report_date: Mapped[datetime | None] = mapped_column(DateTime, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
