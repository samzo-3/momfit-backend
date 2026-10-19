"""테스트 공통 픽스처. 테스트는 SQLite in-memory DB를 사용한다."""

import os
import re
from collections.abc import Generator

# 설정은 import 시점에 읽히므로 앱 모듈을 불러오기 전에 테스트용 값을 둔다.
os.environ.setdefault("JWT_SECRET", "test-secret-not-for-production-use-0123456789")
os.environ.setdefault("COOKIE_SECURE", "false")

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

import models  # noqa: F401
from db.base import Base
from db.session import get_db
from main import app
from services.mailer import Mail, get_mailer


@pytest.fixture()
def db_session() -> Generator[Session, None, None]:
    """테스트마다 새로 만들어지는 in-memory DB 세션."""
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    testing_session = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = testing_session()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


class FakeMailer:
    """발송 요청을 메모리에 모으는 테스트용 메일러."""

    def __init__(self) -> None:
        self.sent: list[Mail] = []

    def send(self, mail: Mail) -> None:
        self.sent.append(mail)

    def last_code(self) -> str:
        """마지막 메일 본문에서 6자리 인증 코드를 꺼낸다."""
        match = re.search(r"\b(\d{6})\b", self.sent[-1].body)
        assert match, "마지막 메일에 인증 코드가 없습니다."
        return match.group(1)


@pytest.fixture()
def mailer() -> FakeMailer:
    return FakeMailer()


@pytest.fixture()
def client(db_session: Session, mailer: FakeMailer) -> Generator[TestClient, None, None]:
    """get_db와 메일러를 테스트용으로 교체한 TestClient."""
    app.dependency_overrides[get_db] = lambda: db_session
    app.dependency_overrides[get_mailer] = lambda: mailer
    yield TestClient(app)
    app.dependency_overrides.clear()
