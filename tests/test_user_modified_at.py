from datetime import timedelta

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from core.clock import today_kst, utc_now
from models.user import User
from tests.helpers import kakao_login, signup_payload

ME = "/api/users/me"
# MySQL DATETIME은 초 단위라, 비교가 어긋나지 않게 마이크로초를 뺀다.
LONG_AGO = (utc_now() - timedelta(days=30)).replace(microsecond=0)


def _signup(client: TestClient) -> str:
    return client.post("/api/auth/signup", json=signup_payload()).json()["access_token"]


def _bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _age(db: Session) -> None:
    """수정일시를 과거로 돌려 놓는다. (명시적으로 지정한 값은 onupdate가 덮어쓰지 않는다)"""
    user = db.get(User, 1)
    user.modified_at = LONG_AGO
    db.commit()


def _modified_at(db: Session):
    db.expire_all()
    return db.get(User, 1).modified_at


def test_가입하면_수정일시가_생성일시와_함께_채워진다(
    client: TestClient, db_session: Session
) -> None:
    _signup(client)

    user = db_session.get(User, 1)
    assert user.modified_at is not None
    assert abs((user.modified_at - user.created_at).total_seconds()) < 1
    assert abs((utc_now() - user.modified_at).total_seconds()) < 5


def test_내_정보를_수정하면_수정일시가_갱신되고_생성일시는_그대로다(
    client: TestClient, db_session: Session
) -> None:
    token = _signup(client)
    created_at = db_session.get(User, 1).created_at
    _age(db_session)

    client.patch(ME, headers=_bearer(token), json={"nickname": "바뀐닉"})

    assert abs((utc_now() - _modified_at(db_session)).total_seconds()) < 5
    assert db_session.get(User, 1).created_at == created_at


def test_출산_예정일과_운동_경험을_수정해도_갱신한다(
    client: TestClient, db_session: Session
) -> None:
    token = _signup(client)
    due = (today_kst() + timedelta(days=100)).isoformat()

    for body in ({"due_date": due}, {"exercise_level": "high"}):
        _age(db_session)
        client.patch(ME, headers=_bearer(token), json=body)
        assert _modified_at(db_session) > LONG_AGO + timedelta(days=1)


def test_수정에_실패하면_수정일시는_그대로다(
    client: TestClient, db_session: Session
) -> None:
    token = _signup(client)
    _age(db_session)

    response = client.patch(ME, headers=_bearer(token), json={"nickname": ""})

    assert response.status_code == 422
    assert _modified_at(db_session) == LONG_AGO


def test_카카오_온보딩을_마치면_수정일시가_갱신된다(
    client: TestClient, db_session: Session
) -> None:
    kakao_login(client)
    token = client.post("/api/auth/refresh").json()["access_token"]
    _age(db_session)

    client.post(
        "/api/users/me/onboarding",
        headers=_bearer(token),
        json={
            "nickname": "카카오맘",
            "due_date": (today_kst() + timedelta(days=84)).isoformat(),
            "exercise_level": "low",
            "consents": {"terms": True, "health_data": True},
        },
    )

    assert abs((utc_now() - _modified_at(db_session)).total_seconds()) < 5


def test_로그인_토큰_갱신_로그아웃_조회는_수정일시를_바꾸지_않는다(
    client: TestClient, db_session: Session
) -> None:
    token = _signup(client)
    _age(db_session)

    client.post("/api/auth/login", json={"login_id": "momfit01", "password": "password1"})
    client.post("/api/auth/refresh")
    client.get(ME, headers=_bearer(token))
    client.post("/api/auth/logout")

    assert _modified_at(db_session) == LONG_AGO


def test_다시_카카오로_로그인해도_수정일시를_바꾸지_않는다(
    client: TestClient, db_session: Session
) -> None:
    kakao_login(client)
    _age(db_session)
    client.cookies.clear()

    kakao_login(client)

    assert _modified_at(db_session) == LONG_AGO


def test_수정일시는_API_응답에_노출하지_않는다(client: TestClient) -> None:
    token = _signup(client)

    body = client.get(ME, headers=_bearer(token)).json()

    assert "modified_at" not in body
