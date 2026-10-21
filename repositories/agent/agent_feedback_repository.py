"""agent_feedback 테이블 접근. 에이전트의 유일한 쓰기 경로다.

팀 리포지토리와 같이 flush까지만 하고 commit은 서비스가 한다.
"""

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from models.agent.agent_feedback import (
    FEEDBACK_TYPE_DAILY,
    FEEDBACK_TYPE_STEP,
    AgentFeedback,
)


def save_step_memo(
    db: Session,
    user_id: int,
    exercise_step_records_id: int | None,
    report_date: datetime,
    step_summary: str,
) -> AgentFeedback:
    """스텝 하나의 '오늘 메모'를 새 STEP 행으로 저장한다.

    같은 스텝·날짜의 이전 메모는 지우지 않고 남겨 둔다. 가장 최근 행이 현재 메모다.
    """
    feedback = AgentFeedback(
        user_id=user_id,
        exercise_step_records_id=exercise_step_records_id,
        feedback_type=FEEDBACK_TYPE_STEP,
        step_summary=step_summary,
        report_date=report_date,
    )
    db.add(feedback)
    db.flush()
    return feedback


def list_step_memos(
    db: Session, user_id: int, report_date: datetime
) -> list[AgentFeedback]:
    """그 날짜의 STEP 메모를 최신 순으로 조회한다.

    agent_feedback에는 exercise_step_id 컬럼이 없어서 '어느 스텝의 메모인가'는
    exercise_step_records_id로만 알 수 있다. 스텝별로 묶는 일은 서비스가 그날의
    팀 스텝 기록(exercise_step_records)과 맞춰서 한다.
    """
    return list(
        db.scalars(
            select(AgentFeedback)
            .where(
                AgentFeedback.user_id == user_id,
                AgentFeedback.feedback_type == FEEDBACK_TYPE_STEP,
                AgentFeedback.report_date == report_date,
            )
            .order_by(AgentFeedback.created_at.desc(), AgentFeedback.id.desc())
        )
    )


def save_daily_report(
    db: Session,
    user_id: int,
    report_date: datetime,
    today_summary: str,
    *,
    created_at: datetime,
) -> AgentFeedback:
    """하루 리포트를 새 DAILY 행으로 저장한다. 저장할 때마다 새 행이 쌓이고, 가장 최근 행이 그날 리포트다.

    created_at에는 저장 시각이 아니라 리포트가 숫자를 센 시각을 넣는다. 저장 시각을 쓰면
    LLM을 기다리는 사이 바뀐 기록을 이미 반영한 것처럼 보게 된다.
    """
    feedback = AgentFeedback(
        user_id=user_id,
        exercise_step_records_id=None,
        feedback_type=FEEDBACK_TYPE_DAILY,
        today_summary=today_summary,
        report_date=report_date,
        created_at=created_at,
    )
    db.add(feedback)
    db.flush()
    return feedback


def list_by_date_range(
    db: Session,
    user_id: int,
    start_date: datetime,
    end_date: datetime,
    feedback_type: str | None = None,
) -> list[AgentFeedback]:
    """기간(start_date 이상, end_date 이하)의 피드백을 오래된 순으로 조회한다.

    다음에 붙일 '기억 꺼내기' 도구(get_recent_days)가 쓴다.
    """
    conditions = [
        AgentFeedback.user_id == user_id,
        AgentFeedback.report_date >= start_date,
        AgentFeedback.report_date <= end_date,
    ]
    if feedback_type is not None:
        conditions.append(AgentFeedback.feedback_type == feedback_type)
    return list(
        db.scalars(
            select(AgentFeedback)
            .where(*conditions)
            .order_by(AgentFeedback.report_date, AgentFeedback.id)
        )
    )


def latest_daily_report(
    db: Session, user_id: int, report_date: datetime
) -> AgentFeedback | None:
    """그 날짜의 가장 최근 DAILY 행. 같은 날 여러 번 요청했을 때 마지막 리포트다."""
    return db.scalars(
        select(AgentFeedback)
        .where(
            AgentFeedback.user_id == user_id,
            AgentFeedback.feedback_type == FEEDBACK_TYPE_DAILY,
            AgentFeedback.report_date == report_date,
        )
        .order_by(AgentFeedback.created_at.desc(), AgentFeedback.id.desc())
    ).first()
