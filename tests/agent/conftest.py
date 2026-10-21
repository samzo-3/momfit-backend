"""에이전트 테스트 공통 픽스처. 팀 tests/conftest.py의 db_session을 그대로 쓴다."""

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session


@pytest.fixture(autouse=True)
def _foreign_keys_on(db_session: Session) -> None:
    """SQLite도 MySQL처럼 FK를 검사하게 한다.

    팀 DB는 MySQL이라 FK를 늘 검사한다. SQLite는 연결마다 켜야 검사해서, 켜지 않으면
    MySQL에서만 터지는 FK 위반을 테스트가 놓친다. (TEST_DATABASE_URL로 MySQL을 쓰면 그대로 둔다)
    """
    if db_session.get_bind().dialect.name == "sqlite":
        db_session.execute(text("PRAGMA foreign_keys=ON"))
