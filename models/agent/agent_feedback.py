"""에이전트 피드백 모델. 팀 최종 ERD의 agent_feedback 테이블이다.

에이전트가 쓰는 유일한 테이블이다. 팀 테이블은 읽기만 한다.
"""

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, Integer, String, Text
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

    DAILY: 사용자에게 보여 준 '오늘의 운동 리포트' 한마디. 그날 기록이 바뀐 뒤 다시 만들면 새 행이
           쌓이고, 가장 최근 행이 그날의 리포트다. 스텝 기록이 없는 날은 저장하지 않는다.
    STEP:  스텝 하나의 '오늘 메모'. 사용자에게 바로 보여 주지 않고, DAILY를 쓸 때 참고한다.
    """

    __tablename__ = "agent_feedback"

    # 팀 최종 ERD대로 BIGINT다. SQLite(테스트·로컬 개발)는 BIGINT 기본키를 자동 증가시키지 않아서
    # SQLite에서만 INTEGER로 만든다.
    id: Mapped[int] = mapped_column(
        BigInteger().with_variant(Integer, "sqlite"),
        primary_key=True,
        autoincrement=True,
    )
    # user_id는 ERD는 BIGINT지만 팀 users.id가 INTEGER라 그 타입을 따른다. (MySQL은 타입이 다른 FK를 만들지 않는다)
    # 팀의 탈퇴 삭제(30일 유예 후 users 행 삭제)가 이 테이블 때문에 막히지 않게 하고,
    # 탈퇴한 사람의 기록도 함께 지워지도록 CASCADE를 둔다.
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    # 팀 최종 ERD대로 NOT NULL이다. ERD는 일일 리포트도 '스텝 수행하면 기록되게' 설계했다.
    # STEP 행에는 그날 그 스텝의 '마지막 시도' 기록 번호를 넣는다. 메모가 어느 시도까지
    # 반영했는지 알려 주는 표시다. DAILY 행에는 그날 모든 스텝 기록 중 마지막 시도 번호를 넣는다.
    # 그래서 스텝 기록이 없는 날(일반 운동만 한 날)의 DAILY는 저장하지 않는다.
    # 팀이 스텝 기록을 지울 때 이 테이블 때문에 막히지 않게 CASCADE로 함께 지운다.
    exercise_step_records_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("exercise_step_records.id", ondelete="CASCADE"),
        nullable=False,
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
