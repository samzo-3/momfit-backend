"""유저·인증 관련 id 컬럼이 MySQL에서 BIGINT로 만들어지는지 확인한다."""

import pytest
from sqlalchemy.dialects import mysql
from sqlalchemy.schema import CreateTable

from models.auth_identity import AuthIdentity
from models.daily_visit import DailyVisit
from models.email_verification import EmailVerification
from models.exercise_record import ExerciseRecord
from models.exercise_step_record import ExerciseStepRecord
from models.refresh_token import RefreshToken
from models.user import User
from models.user_goal import UserGoal

BIGINT_COLUMNS = [
    (User, "id"),
    (AuthIdentity, "id"),
    (AuthIdentity, "user_id"),
    (RefreshToken, "id"),
    (RefreshToken, "user_id"),
    (EmailVerification, "id"),
    (UserGoal, "user_id"),
    (ExerciseRecord, "user_id"),
    (ExerciseStepRecord, "user_id"),
    (DailyVisit, "user_id"),
]


@pytest.mark.parametrize(("model", "column"), BIGINT_COLUMNS)
def test_id_columns_are_bigint_on_mysql(model, column):
    ddl = str(CreateTable(model.__table__).compile(dialect=mysql.dialect()))
    assert f"{column} BIGINT" in ddl
