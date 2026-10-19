"""테스트 공통 픽스처. 테스트는 SQLite in-memory DB를 사용한다."""

import os
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


@pytest.fixture()
def client(db_session: Session) -> Generator[TestClient, None, None]:
    """get_db를 테스트 세션으로 교체한 TestClient."""
    app.dependency_overrides[get_db] = lambda: db_session
    yield TestClient(app)
    app.dependency_overrides.clear()
