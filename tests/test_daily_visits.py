"""로그인·토큰 갱신이 일별 방문(daily_visits)으로 기록되는지 검사한다."""

from datetime import date, datetime, timedelta

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from core.clock import kst_date, utc_now
from models.daily_visit import DailyVisit
from repositories import daily_visit_repository
from services.auth import account_service
from tests.helpers import kakao_login, signup_payload


def _visits(db: Session) -> list[tuple[date, int]]:
    return [(v.visit_date, v.user_id) for v in db.query(DailyVisit).order_by(DailyVisit.visit_date)]


def test_kst_date는_UTC_15시부터_다음날이다() -> None:
    assert kst_date(datetime(2026, 10, 21, 14, 59)) == date(2026, 10, 21)
    assert kst_date(datetime(2026, 10, 21, 15, 0)) == date(2026, 10, 22)


def test_가입하면_오늘_방문이_기록된다(client: TestClient, db_session: Session) -> None:
    client.post("/api/auth/signup", json=signup_payload())

    assert _visits(db_session) == [(kst_date(utc_now()), 1)]


def test_같은_날_로그인과_갱신을_반복해도_한_행이다(
    client: TestClient, db_session: Session
) -> None:
    client.post("/api/auth/signup", json=signup_payload())
    client.post("/api/auth/login", json={"login_id": "momfit01", "password": "password1"})
    client.post("/api/auth/refresh")
    client.post("/api/auth/refresh")

    assert len(_visits(db_session)) == 1


def test_날짜가_바뀐_뒤_갱신하면_새_행이_생긴다(
    client: TestClient, db_session: Session
) -> None:
    client.post("/api/auth/signup", json=signup_payload())
    yesterday = kst_date(utc_now()) - timedelta(days=1)
    db_session.query(DailyVisit).update({"visit_date": yesterday})
    db_session.commit()

    client.post("/api/auth/refresh")

    assert [d for d, _ in _visits(db_session)] == [yesterday, kst_date(utc_now())]


def test_사용자마다_따로_기록된다(client: TestClient, db_session: Session) -> None:
    client.post("/api/auth/signup", json=signup_payload())
    client.post(
        "/api/auth/signup",
        json=signup_payload(login_id="momfit02", email="mom2@example.com"),
    )

    assert sorted(user_id for _, user_id in _visits(db_session)) == [1, 2]


def test_카카오_로그인도_방문으로_기록된다(client: TestClient, db_session: Session) -> None:
    kakao_login(client)

    assert _visits(db_session) == [(kst_date(utc_now()), 1)]


def test_이미_있는_방문을_다시_기록해도_오류가_없다(
    client: TestClient, db_session: Session
) -> None:
    client.post("/api/auth/signup", json=signup_payload())
    day = date(2026, 1, 1)

    daily_visit_repository.record(db_session, 1, day)
    db_session.commit()
    daily_visit_repository.record(db_session, 1, day)
    db_session.commit()

    assert (day, 1) in _visits(db_session)
    assert len(_visits(db_session)) == 2  # 가입 때 기록된 오늘 방문 + 위에서 기록한 날짜


def test_계정이_삭제되면_방문_기록도_삭제된다(
    client: TestClient, db_session: Session
) -> None:
    token = client.post("/api/auth/signup", json=signup_payload()).json()["access_token"]
    client.delete("/api/users/me", headers={"Authorization": f"Bearer {token}"})

    count = account_service.purge_expired(
        db_session, now=utc_now() + timedelta(days=3650)
    )

    assert count == 1
    assert _visits(db_session) == []
