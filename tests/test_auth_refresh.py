from datetime import timedelta

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from core.clock import utc_now
from models.refresh_token import RefreshToken
from tests.helpers import signup_payload

COOKIE = "refresh_token"


def _signup_and_get_refresh(client: TestClient) -> str:
    response = client.post("/api/auth/signup", json=signup_payload())
    assert response.status_code == 201
    return response.cookies[COOKIE]


def _use_cookie(client: TestClient, value: str | None) -> None:
    client.cookies.clear()
    if value is not None:
        client.cookies.set(COOKIE, value, path="/api/auth")


def test_refresh하면_새_access와_새_refresh를_받는다(client: TestClient) -> None:
    old = _signup_and_get_refresh(client)

    response = client.post("/api/auth/refresh")

    assert response.status_code == 200
    assert response.json()["access_token"]
    assert response.cookies[COOKIE] != old


def test_토큰은_DB에_해시로만_저장된다(client: TestClient, db_session: Session) -> None:
    raw = _signup_and_get_refresh(client)

    stored = db_session.query(RefreshToken).one()

    assert stored.token_hash != raw
    assert raw not in stored.token_hash


def test_쿠키가_없으면_REFRESH_INVALID(client: TestClient) -> None:
    response = client.post("/api/auth/refresh")

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "REFRESH_INVALID"


def test_알_수_없는_토큰은_REFRESH_INVALID(client: TestClient) -> None:
    _use_cookie(client, "unknown-token")

    response = client.post("/api/auth/refresh")

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "REFRESH_INVALID"


def test_사용된_토큰을_다시_쓰면_family_전체가_폐기된다(client: TestClient) -> None:
    first = _signup_and_get_refresh(client)
    second = client.post("/api/auth/refresh").cookies[COOKIE]

    # 이미 교체된 첫 토큰을 다시 사용 → 탈취로 간주
    _use_cookie(client, first)
    reused = client.post("/api/auth/refresh")
    assert reused.status_code == 401
    assert reused.json()["error"]["code"] == "REFRESH_INVALID"

    # 정상적으로 발급된 최신 토큰도 함께 무효화된다.
    _use_cookie(client, second)
    assert client.post("/api/auth/refresh").status_code == 401


def test_다른_로그인의_토큰은_영향받지_않는다(client: TestClient) -> None:
    first = _signup_and_get_refresh(client)
    client.cookies.clear()
    other_device = client.post(
        "/api/auth/login", json={"login_id": "momfit01", "password": "password1"}
    ).cookies[COOKIE]
    _use_cookie(client, first)
    client.post("/api/auth/refresh")
    _use_cookie(client, first)
    client.post("/api/auth/refresh")  # first family 폐기

    _use_cookie(client, other_device)

    assert client.post("/api/auth/refresh").status_code == 200


def test_만료된_토큰은_REFRESH_INVALID(client: TestClient, db_session: Session) -> None:
    _signup_and_get_refresh(client)
    db_session.query(RefreshToken).one().expires_at = utc_now() - timedelta(seconds=1)
    db_session.commit()

    response = client.post("/api/auth/refresh")

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "REFRESH_INVALID"


def test_로그아웃하면_204와_함께_토큰이_폐기된다(client: TestClient) -> None:
    raw = _signup_and_get_refresh(client)

    response = client.post("/api/auth/logout")

    assert response.status_code == 204
    assert "Max-Age=0" in response.headers["set-cookie"]
    _use_cookie(client, raw)
    assert client.post("/api/auth/refresh").status_code == 401


def test_쿠키_없이_로그아웃해도_204(client: TestClient) -> None:
    assert client.post("/api/auth/logout").status_code == 204
