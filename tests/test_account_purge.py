"""유예 기간이 지난 탈퇴 계정의 완전 삭제와 주기 작업."""

import asyncio
import dataclasses
from datetime import timedelta

import pytest
from fastapi import FastAPI
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

import main
from core.clock import utc_now
from core.config import settings
from models.auth_identity import AuthIdentity
from models.email_verification import EmailVerification
from models.refresh_token import RefreshToken
from models.user import User
from services import account_service
from tests.conftest import FakeMailer
from tests.helpers import signup_payload

ME = "/api/users/me"
GRACE = timedelta(days=settings.account_grace_days)


def _signup(client, **overrides) -> str:
    response = client.post("/api/auth/signup", json=signup_payload(**overrides))
    assert response.status_code == 201
    return response.json()["access_token"]


def _withdraw(client, db_session: Session, ago: timedelta, **overrides) -> None:
    """가입해서 탈퇴시키고, 탈퇴 시각을 ago 전으로 되돌린다."""
    token = _signup(client, **overrides)
    client.delete(ME, headers={"Authorization": f"Bearer {token}"})
    login_id = overrides.get("login_id", "momfit01")
    user = (
        db_session.query(User)
        .join(AuthIdentity)
        .filter(AuthIdentity.login_id == login_id)
        .one()
    )
    user.withdrawn_at = utc_now() - ago
    db_session.commit()


def test_유예_기간이_지난_계정은_모든_데이터가_삭제된다(
    client, db_session: Session, mailer: FakeMailer
) -> None:
    client.post(
        "/api/auth/email/send-code",
        json={"email": "mom@example.com", "purpose": "signup"},
    )
    _withdraw(client, db_session, GRACE + timedelta(minutes=1))

    count = account_service.purge_expired(db_session)

    assert count == 1
    db_session.expire_all()
    assert db_session.query(User).count() == 0
    assert db_session.query(AuthIdentity).count() == 0
    assert db_session.query(RefreshToken).count() == 0
    assert db_session.query(EmailVerification).count() == 0


def test_유예_기간_안의_계정은_삭제하지_않는다(client, db_session: Session) -> None:
    _withdraw(client, db_session, GRACE - timedelta(minutes=1))

    count = account_service.purge_expired(db_session)

    assert count == 0
    assert db_session.query(User).count() == 1


def test_유예_기간이_정확히_끝난_시각부터_삭제한다(client, db_session: Session) -> None:
    _withdraw(client, db_session, timedelta(0))
    user = db_session.query(User).one()
    exactly = user.withdrawn_at + GRACE

    assert account_service.purge_expired(db_session, now=exactly - timedelta(seconds=1)) == 0
    assert account_service.purge_expired(db_session, now=exactly) == 1


def test_이용_중인_계정은_삭제하지_않는다(client, db_session: Session) -> None:
    _signup(client)
    user = db_session.query(User).one()
    # 상태가 active이면 withdrawn_at이 비어 있다. 값이 있어도 active면 건드리지 않는다.
    user.withdrawn_at = utc_now() - GRACE - timedelta(days=100)
    db_session.commit()

    assert account_service.purge_expired(db_session) == 0
    assert db_session.query(User).count() == 1


def test_만료된_계정만_삭제하고_다른_계정은_남긴다(client, db_session: Session) -> None:
    _withdraw(client, db_session, GRACE + timedelta(days=1))
    _withdraw(
        client,
        db_session,
        timedelta(days=1),
        login_id="momfit02",
        email="recent@example.com",
    )
    _signup(client, login_id="momfit03", email="active@example.com")

    count = account_service.purge_expired(db_session)

    assert count == 1
    emails = sorted(u.email for u in db_session.query(User).all())
    assert emails == ["active@example.com", "recent@example.com"]
    assert db_session.query(AuthIdentity).count() == 2


def test_삭제된_뒤에는_같은_아이디와_이메일로_다시_가입할_수_있다(
    client, db_session: Session
) -> None:
    _withdraw(client, db_session, GRACE + timedelta(days=1))
    account_service.purge_expired(db_session)

    response = client.post("/api/auth/signup", json=signup_payload())

    assert response.status_code == 201


def test_삭제를_여러_번_실행해도_안전하다(client, db_session: Session) -> None:
    _withdraw(client, db_session, GRACE + timedelta(days=1))

    assert account_service.purge_expired(db_session) == 1
    assert account_service.purge_expired(db_session) == 0


def test_유예_기간은_설정으로_바꿀_수_있다(
    client, db_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    _withdraw(client, db_session, timedelta(days=8))
    assert account_service.purge_expired(db_session) == 0

    monkeypatch.setattr(
        account_service, "settings", dataclasses.replace(settings, account_grace_days=7)
    )

    assert account_service.purge_expired(db_session) == 1


class _SessionContext:
    """run_purge가 자체 세션 대신 테스트 세션을 쓰도록 하는 SessionLocal 대역."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def __call__(self) -> "_SessionContext":
        return self

    def __enter__(self) -> Session:
        return self._session

    def __exit__(self, *_args: object) -> None:
        return None


def test_run_purge는_자체_세션으로_삭제하고_개수를_돌려준다(
    client, db_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    _withdraw(client, db_session, GRACE + timedelta(days=1))
    monkeypatch.setattr("db.session.SessionLocal", _SessionContext(db_session))

    assert account_service.run_purge() == 1
    assert db_session.query(User).count() == 0


def test_run_purge는_삭제한_개수를_로그로_남긴다(
    client,
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    _withdraw(client, db_session, GRACE + timedelta(days=1))
    monkeypatch.setattr("db.session.SessionLocal", _SessionContext(db_session))

    with caplog.at_level("INFO"):
        account_service.run_purge()

    assert "1건" in caplog.text


def test_수동_실행_스크립트는_삭제한_개수를_출력한다(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    from scripts import purge_withdrawn

    monkeypatch.setattr(purge_withdrawn, "run_purge", lambda: 3)

    purge_withdrawn.main()

    assert "3건" in capsys.readouterr().out


class TestPeriodicPurge:
    def test_주기마다_삭제를_실행하고_실패해도_계속_돈다(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        calls: list[int] = []
        sleeps: list[float] = []

        def fake_purge() -> int:
            calls.append(1)
            if len(calls) == 1:
                raise RuntimeError("DB 연결 실패")
            return 0

        async def fake_sleep(seconds: float) -> None:
            sleeps.append(seconds)
            if len(sleeps) == 2:
                raise asyncio.CancelledError

        monkeypatch.setattr(main, "run_purge", fake_purge)
        monkeypatch.setattr(main.asyncio, "sleep", fake_sleep)

        with pytest.raises(asyncio.CancelledError):
            asyncio.run(main._purge_periodically(6))

        assert len(calls) == 2
        assert sleeps == [6 * 60 * 60, 6 * 60 * 60]

    def _run_lifespan(
        self, monkeypatch: pytest.MonkeyPatch, interval_hours: int
    ) -> list[str]:
        events: list[str] = []

        async def fake_loop(hours: int) -> None:
            events.append(f"start:{hours}")
            try:
                await asyncio.sleep(3600)
            except asyncio.CancelledError:
                events.append("cancelled")
                raise

        monkeypatch.setattr(main, "_purge_periodically", fake_loop)
        monkeypatch.setattr(main, "engine", create_engine("sqlite://"))
        monkeypatch.setattr(
            main,
            "settings",
            dataclasses.replace(
                settings, account_purge_interval_hours=interval_hours
            ),
        )

        async def run() -> None:
            async with main.lifespan(FastAPI()):
                await asyncio.sleep(0)

        asyncio.run(run())
        return events

    def test_서버가_시작되면_주기_작업을_켜고_끝나면_멈춘다(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        assert self._run_lifespan(monkeypatch, 6) == ["start:6", "cancelled"]

    def test_주기가_0이면_주기_작업을_켜지_않는다(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        assert self._run_lifespan(monkeypatch, 0) == []
