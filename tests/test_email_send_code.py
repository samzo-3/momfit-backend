from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from core.clock import utc_now
from core.errors import AppError
from models.email_verification import EmailVerification
from services import email_verification_service as service
from tests.conftest import FakeMailer
from tests.helpers import signup_payload

SEND = "/api/auth/email/send-code"


def _send(client: TestClient, email: str = "mom@example.com", purpose: str = "signup"):
    return client.post(SEND, json={"email": email, "purpose": purpose})


def test_가입용_코드를_보내면_204와_함께_메일이_발송된다(
    client: TestClient, mailer: FakeMailer
) -> None:
    response = _send(client)

    assert response.status_code == 204
    assert response.content == b""
    assert len(mailer.sent) == 1
    assert mailer.sent[0].to == "mom@example.com"
    assert "회원가입" in mailer.sent[0].subject
    assert len(mailer.last_code()) == 6


def test_코드는_해시로만_저장된다(
    client: TestClient, mailer: FakeMailer, db_session: Session
) -> None:
    _send(client)

    stored = db_session.query(EmailVerification).one()
    assert mailer.last_code() not in stored.code_hash
    assert len(stored.code_hash) == 64
    assert stored.attempts == 0
    assert stored.consumed_at is None
    assert stored.expires_at - stored.created_at == timedelta(minutes=10)


def test_이메일은_정규화되어_저장된다(client: TestClient, db_session: Session) -> None:
    _send(client, email="  Mom@Example.COM ")

    assert db_session.query(EmailVerification).one().email == "mom@example.com"


def test_요청한_IP가_기록된다(client: TestClient, db_session: Session) -> None:
    _send(client)

    assert db_session.query(EmailVerification).one().ip == "testclient"


def test_이미_가입된_이메일은_메일을_보내지_않지만_응답은_같다(
    client: TestClient, mailer: FakeMailer, db_session: Session
) -> None:
    new_email = _send(client, email="new@example.com")
    client.post("/api/auth/signup", json=signup_payload())
    mailer.sent.clear()

    existing = _send(client, email="mom@example.com")

    assert existing.status_code == new_email.status_code == 204
    assert existing.content == new_email.content
    assert mailer.sent == []
    # 제한 계산을 위해 기록은 남는다.
    assert db_session.query(EmailVerification).filter_by(email="mom@example.com").count() == 1


def test_비밀번호_재설정은_가입된_이메일에만_메일을_보낸다(
    client: TestClient, mailer: FakeMailer
) -> None:
    unknown = _send(client, email="nobody@example.com", purpose="password_reset")
    assert unknown.status_code == 204
    assert mailer.sent == []

    client.post("/api/auth/signup", json=signup_payload())
    known = _send(client, email="mom@example.com", purpose="password_reset")

    assert known.status_code == 204
    assert len(mailer.sent) == 1
    assert "비밀번호" in mailer.sent[0].subject


def test_60초_안에_다시_요청하면_429와_Retry_After(client: TestClient) -> None:
    _send(client)

    response = _send(client)

    assert response.status_code == 429
    assert response.json()["error"]["code"] == "RATE_LIMITED"
    assert 0 < int(response.headers["Retry-After"]) <= 60


def test_제한은_가입_여부와_상관없이_같게_적용된다(client: TestClient) -> None:
    client.post("/api/auth/signup", json=signup_payload())

    _send(client, email="mom@example.com")
    again = _send(client, email="mom@example.com")
    _send(client, email="nobody@example.com")
    again_unknown = _send(client, email="nobody@example.com")

    assert again.status_code == again_unknown.status_code == 429


@pytest.mark.parametrize(
    "body",
    [
        {"email": "not-an-email", "purpose": "signup"},
        {"email": "a@b.com", "purpose": "other"},
        {"purpose": "signup"},
    ],
)
def test_잘못된_요청은_422(client: TestClient, body: dict[str, str]) -> None:
    assert client.post(SEND, json=body).status_code == 422


def test_메일_발송이_실패해도_응답은_204(client: TestClient, mailer: FakeMailer) -> None:
    def fail(_):
        raise ConnectionError("smtp down")

    mailer.send = fail  # type: ignore[method-assign]

    assert _send(client).status_code == 204


class TestRateLimitService:
    """시간을 직접 지정해 일일 제한과 재발송 간격을 검증한다."""

    NOW = datetime(2026, 10, 19, 12, 0, 0)

    def _send(self, db: Session, email: str = "a@b.com", ip: str | None = "1.1.1.1", at: datetime | None = None):
        return service.send_code(db, email, "signup", ip, now=at or self.NOW)

    def test_60초가_지나면_다시_보낼_수_있다(self, db_session: Session) -> None:
        self._send(db_session)

        assert self._send(db_session, at=self.NOW + timedelta(seconds=60)) is not None

    def test_59초에는_거절한다(self, db_session: Session) -> None:
        self._send(db_session)

        with pytest.raises(AppError) as exc_info:
            self._send(db_session, at=self.NOW + timedelta(seconds=59))

        assert exc_info.value.status_code == 429

    def test_이메일당_하루_5회를_넘으면_거절한다(self, db_session: Session) -> None:
        for i in range(5):
            self._send(db_session, at=self.NOW + timedelta(minutes=i * 2))

        with pytest.raises(AppError) as exc_info:
            self._send(db_session, at=self.NOW + timedelta(minutes=12))

        assert exc_info.value.code == "RATE_LIMITED"

    def test_하루가_지나면_횟수가_초기화된다(self, db_session: Session) -> None:
        for i in range(5):
            self._send(db_session, at=self.NOW + timedelta(minutes=i * 2))

        assert self._send(db_session, at=self.NOW + timedelta(days=1, minutes=9)) is not None

    def test_IP당_하루_20회를_넘으면_이메일이_달라도_거절한다(self, db_session: Session) -> None:
        for i in range(20):
            self._send(db_session, email=f"user{i}@b.com", at=self.NOW + timedelta(seconds=i))

        with pytest.raises(AppError) as exc_info:
            self._send(db_session, email="another@b.com", at=self.NOW + timedelta(seconds=30))

        assert exc_info.value.code == "RATE_LIMITED"

    def test_다른_IP는_영향받지_않는다(self, db_session: Session) -> None:
        for i in range(20):
            self._send(db_session, email=f"user{i}@b.com", at=self.NOW + timedelta(seconds=i))

        assert self._send(db_session, email="another@b.com", ip="2.2.2.2", at=self.NOW + timedelta(seconds=30)) is not None

    def test_새_코드를_발급하면_이전_코드는_무효화된다(self, db_session: Session) -> None:
        self._send(db_session)
        self._send(db_session, at=self.NOW + timedelta(seconds=61))

        rows = db_session.query(EmailVerification).order_by(EmailVerification.id).all()
        assert rows[0].consumed_at is not None
        assert rows[1].consumed_at is None


def test_utc_now_기반_기록_시각(db_session: Session) -> None:
    service.send_code(db_session, "a@b.com", "signup", None)

    created = db_session.query(EmailVerification).one().created_at
    assert abs((utc_now() - created).total_seconds()) < 5
