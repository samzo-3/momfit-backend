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
from services.auth.kakao_client import KakaoProfile, get_kakao_client
from services.auth.mailer import Mail, get_mailer


@pytest.fixture()
def db_session() -> Generator[Session, None, None]:
    """테스트마다 새로 만들어지는 DB 세션. 기본은 SQLite in-memory이고,
    TEST_DATABASE_URL을 주면 그 DB(예: MySQL)에서 테이블을 만들고 지우며 실행한다."""
    url = os.getenv("TEST_DATABASE_URL")
    if url:
        engine = create_engine(url, pool_pre_ping=True)
        Base.metadata.drop_all(engine)
    else:
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
        if url:
            Base.metadata.drop_all(engine)
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


class FakeKakaoClient:
    """카카오 API 호출을 흉내 내는 테스트용 클라이언트. 호출 기록과 실패 주입을 지원한다."""

    def __init__(self) -> None:
        self.profile = KakaoProfile(id="12345", nickname="카카오맘")
        self.exchanged_codes: list[str] = []
        self.unlinked: list[str] = []
        self.fail_authorize: Exception | None = None
        self.fail_exchange: Exception | None = None
        self.fail_profile: Exception | None = None
        self.fail_unlink: Exception | None = None

    def authorize_url(self, state: str) -> str:
        if self.fail_authorize:
            raise self.fail_authorize
        return f"https://kauth.kakao.com/oauth/authorize?client_id=test&state={state}"

    def exchange_code(self, code: str) -> str:
        self.exchanged_codes.append(code)
        if self.fail_exchange:
            raise self.fail_exchange
        return "kakao-access-token"

    def fetch_profile(self, access_token: str) -> KakaoProfile:
        assert access_token == "kakao-access-token"
        if self.fail_profile:
            raise self.fail_profile
        return self.profile

    def unlink(self, kakao_user_id: str) -> None:
        if self.fail_unlink:
            raise self.fail_unlink
        self.unlinked.append(kakao_user_id)


@pytest.fixture()
def mailer() -> FakeMailer:
    return FakeMailer()


@pytest.fixture()
def kakao() -> FakeKakaoClient:
    return FakeKakaoClient()


@pytest.fixture()
def client(
    db_session: Session, mailer: FakeMailer, kakao: FakeKakaoClient
) -> Generator[TestClient, None, None]:
    """get_db, 메일러, 카카오 클라이언트를 테스트용으로 교체한 TestClient."""
    app.dependency_overrides[get_db] = lambda: db_session
    app.dependency_overrides[get_mailer] = lambda: mailer
    app.dependency_overrides[get_kakao_client] = lambda: kakao
    yield TestClient(app)
    app.dependency_overrides.clear()
