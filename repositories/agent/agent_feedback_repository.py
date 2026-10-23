"""에이전트 피드백 테이블 접근. 에이전트의 유일한 쓰기 경로다.

팀 최종 ERD의 agent_step_feedback, agent_daily_feedback, daily_feedback_sources를 다룬다.
팀 리포지토리와 같이 flush까지만 하고 commit은 서비스가 한다.
"""

from collections.abc import Iterable
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from models.agent.agent_daily_feedback import AgentDailyFeedback
from models.agent.agent_step_feedback import AgentStepFeedback
from models.agent.daily_feedback_source import DailyFeedbackSource


def save_step_memo(
    db: Session,
    user_id: int,
    exercise_step_records_id: int,
    step_summary: str,
) -> AgentStepFeedback:
    """스텝 하나의 '오늘 메모'를 새 행으로 저장한다.

    같은 스텝의 이전 메모는 지우지 않고 남겨 둔다. 가장 최근 행이 현재 메모다.
    """
    feedback = AgentStepFeedback(
        user_id=user_id,
        exercise_step_records_id=exercise_step_records_id,
        step_summary=step_summary,
    )
    db.add(feedback)
    db.flush()
    return feedback


def list_step_memos(
    db: Session, user_id: int, step_record_ids: Iterable[int]
) -> list[AgentStepFeedback]:
    """주어진 스텝 기록들에 붙은 메모를 최신 순으로 조회한다.

    agent_step_feedback에는 날짜와 exercise_step_id 컬럼이 없어서, 부르는 쪽이 그날의 팀 스텝 기록
    번호를 넘긴다. 스텝별로 묶는 일은 서비스가 그 스텝 기록(exercise_step_records)과 맞춰서 한다.
    """
    ids = list(step_record_ids)
    if not ids:
        return []
    return list(
        db.scalars(
            select(AgentStepFeedback)
            .where(
                AgentStepFeedback.user_id == user_id,
                AgentStepFeedback.exercise_step_records_id.in_(ids),
            )
            .order_by(AgentStepFeedback.created_at.desc(), AgentStepFeedback.id.desc())
        )
    )


def save_daily_report(
    db: Session,
    user_id: int,
    report_date: datetime,
    today_summary: str,
    *,
    created_at: datetime,
    step_feedback_ids: Iterable[int] = (),
) -> AgentDailyFeedback:
    """하루 리포트를 새 행으로 저장한다. 저장할 때마다 새 행이 쌓이고, 가장 최근 행이 그날 리포트다.

    created_at에는 저장 시각이 아니라 리포트가 숫자를 센 시각을 넣는다. 저장 시각을 쓰면
    LLM을 기다리는 사이 바뀐 기록을 이미 반영한 것처럼 보게 된다.
    step_feedback_ids에는 한마디가 참고한 스텝 메모 번호를 넘기고, daily_feedback_sources에 잇는다.
    """
    feedback = AgentDailyFeedback(
        user_id=user_id,
        today_summary=today_summary,
        report_date=report_date,
        created_at=created_at,
        modified_at=created_at,
    )
    db.add(feedback)
    db.flush()
    db.add_all(
        DailyFeedbackSource(
            agent_daily_feedback_id=feedback.id, agent_step_feedback_id=step_feedback_id
        )
        for step_feedback_id in sorted(set(step_feedback_ids))
    )
    db.flush()
    return feedback


def list_daily_feedback_sources(
    db: Session, agent_daily_feedback_id: int
) -> list[int]:
    """일일 리포트 하나가 참고한 스텝 메모 번호들."""
    return list(
        db.scalars(
            select(DailyFeedbackSource.agent_step_feedback_id)
            .where(DailyFeedbackSource.agent_daily_feedback_id == agent_daily_feedback_id)
            .order_by(DailyFeedbackSource.agent_step_feedback_id)
        )
    )


def list_daily_reports(
    db: Session,
    user_id: int,
    start_date: datetime,
    end_date: datetime,
) -> list[AgentDailyFeedback]:
    """기간(start_date 이상, end_date 이하)의 일일 리포트를 오래된 순으로 조회한다.

    다음에 붙일 '기억 꺼내기' 도구(get_recent_days)가 쓴다.
    """
    return list(
        db.scalars(
            select(AgentDailyFeedback)
            .where(
                AgentDailyFeedback.user_id == user_id,
                AgentDailyFeedback.report_date >= start_date,
                AgentDailyFeedback.report_date <= end_date,
            )
            .order_by(AgentDailyFeedback.report_date, AgentDailyFeedback.id)
        )
    )


def latest_daily_report(
    db: Session, user_id: int, report_date: datetime
) -> AgentDailyFeedback | None:
    """그 날짜의 가장 최근 리포트. 같은 날 여러 번 요청했을 때 마지막 리포트다."""
    return db.scalars(
        select(AgentDailyFeedback)
        .where(
            AgentDailyFeedback.user_id == user_id,
            AgentDailyFeedback.report_date == report_date,
        )
        .order_by(AgentDailyFeedback.created_at.desc(), AgentDailyFeedback.id.desc())
    ).first()
