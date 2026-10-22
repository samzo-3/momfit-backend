"""에이전트 테이블 셋이 팀 최종 ERD와 같은지 확인한다.

ERD 원문에는 AUTO_INCREMENT와 FK 제약이 빠져 있어서(설계 도구 내보내기 형식) 주석의
"Auto Increment", "FK"를 따른다. ON DELETE CASCADE는 ERD가 정하지 않은 부분이라 사용자 승인을 받고 뒀다.
"""

import pytest
from sqlalchemy.dialects import mysql

from models.agent.agent_daily_feedback import AgentDailyFeedback
from models.agent.agent_step_feedback import AgentStepFeedback
from models.agent.daily_feedback_source import DailyFeedbackSource

# 팀 최종 ERD의 컬럼: 이름 → (MySQL 타입, NULL 허용)
ERD_COLUMNS = {
    AgentStepFeedback: {
        "id": ("BIGINT", False),
        "user_id": ("BIGINT", False),
        "exercise_step_records_id": ("BIGINT", False),
        "step_summary": ("TEXT", True),
        "created_at": ("DATETIME", False),
    },
    AgentDailyFeedback: {
        "id": ("BIGINT", False),
        "user_id": ("BIGINT", False),
        "today_summary": ("VARCHAR(255)", True),
        "report_date": ("DATETIME", True),
        "created_at": ("DATETIME", True),
        "modified_at": ("DATETIME", True),
    },
    DailyFeedbackSource: {
        "id": ("BIGINT", False),
        "agent_daily_feedback_id": ("BIGINT", False),
        "agent_step_feedback_id": ("BIGINT", False),
    },
}

# 주석이 "FK"인 컬럼 → 가리키는 컬럼
ERD_FOREIGN_KEYS = {
    AgentStepFeedback: {
        "user_id": "users.id",
        "exercise_step_records_id": "exercise_step_records.id",
    },
    AgentDailyFeedback: {"user_id": "users.id"},
    DailyFeedbackSource: {
        "agent_daily_feedback_id": "agent_daily_feedback.id",
        "agent_step_feedback_id": "agent_step_feedback.id",
    },
}


@pytest.mark.parametrize("model", list(ERD_COLUMNS), ids=lambda m: m.__tablename__)
def test_컬럼_이름_타입_NULL_여부가_ERD와_같다(model) -> None:
    dialect = mysql.dialect()
    actual = {
        column.name: (column.type.compile(dialect=dialect), column.nullable)
        for column in model.__table__.columns
    }

    assert actual == ERD_COLUMNS[model]


@pytest.mark.parametrize("model", list(ERD_COLUMNS), ids=lambda m: m.__tablename__)
def test_id는_자동_증가_기본키다(model) -> None:
    (primary_key,) = model.__table__.primary_key.columns

    assert primary_key.name == "id"
    assert primary_key.autoincrement is True


@pytest.mark.parametrize("model", list(ERD_FOREIGN_KEYS), ids=lambda m: m.__tablename__)
def test_FK는_ERD와_같고_모두_CASCADE다(model) -> None:
    actual = {
        fk.parent.name: (fk.target_fullname, fk.ondelete)
        for fk in model.__table__.foreign_keys
    }

    assert actual == {
        column: (target, "CASCADE") for column, target in ERD_FOREIGN_KEYS[model].items()
    }
