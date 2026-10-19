from fastapi.testclient import TestClient

from core.security import create_email_verification_token
from tests.conftest import FakeMailer
from tests.helpers import signup_payload

RESET = "/api/auth/password/reset"


def _signup(client: TestClient) -> str:
    response = client.post("/api/auth/signup", json=signup_payload())
    assert response.status_code == 201
    return response.cookies["refresh_token"]


def _login(client: TestClient, password: str):
    client.cookies.clear()
    return client.post(
        "/api/auth/login", json={"login_id": "momfit01", "password": password}
    )


def _reset_token(client: TestClient, mailer: FakeMailer, email="mom@example.com") -> str:
    client.post("/api/auth/email/send-code", json={"email": email, "purpose": "password_reset"})
    code = mailer.last_code()
    return client.post(
        "/api/auth/email/verify-code",
        json={"email": email, "code": code, "purpose": "password_reset"},
    ).json()["email_verification_token"]


def test_이메일_인증_후_비밀번호를_재설정한다(client: TestClient, mailer: FakeMailer) -> None:
    _signup(client)
    token = _reset_token(client, mailer)

    response = client.post(
        RESET,
        json={"email": "mom@example.com", "email_verification_token": token, "new_password": "newpass99"},
    )

    assert response.status_code == 204
    assert _login(client, "password1").status_code == 401
    assert _login(client, "newpass99").status_code == 200


def test_재설정하면_기존_기기의_로그인이_해제된다(client: TestClient, mailer: FakeMailer) -> None:
    old_refresh = _signup(client)
    token = _reset_token(client, mailer)
    client.post(
        RESET,
        json={"email": "mom@example.com", "email_verification_token": token, "new_password": "newpass99"},
    )

    client.cookies.clear()
    client.cookies.set("refresh_token", old_refresh, path="/api/auth")

    response = client.post("/api/auth/refresh")

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "REFRESH_INVALID"


def test_가입용_토큰으로는_재설정할_수_없다(client: TestClient) -> None:
    _signup(client)
    token = create_email_verification_token("mom@example.com", "signup")

    response = client.post(
        RESET,
        json={"email": "mom@example.com", "email_verification_token": token, "new_password": "newpass99"},
    )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "EMAIL_TOKEN_INVALID"
    assert _login(client, "password1").status_code == 200


def test_다른_이메일의_토큰으로는_재설정할_수_없다(client: TestClient) -> None:
    _signup(client)
    token = create_email_verification_token("other@example.com", "password_reset")

    response = client.post(
        RESET,
        json={"email": "mom@example.com", "email_verification_token": token, "new_password": "newpass99"},
    )

    assert response.json()["error"]["code"] == "EMAIL_TOKEN_INVALID"


def test_가입되지_않은_이메일은_EMAIL_TOKEN_INVALID(client: TestClient) -> None:
    token = create_email_verification_token("nobody@example.com", "password_reset")

    response = client.post(
        RESET,
        json={"email": "nobody@example.com", "email_verification_token": token, "new_password": "newpass99"},
    )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "EMAIL_TOKEN_INVALID"


def test_새_비밀번호가_규칙에_맞지_않으면_422(client: TestClient) -> None:
    _signup(client)
    token = create_email_verification_token("mom@example.com", "password_reset")

    for password in ("short1", "onlyletters", "12345678"):
        response = client.post(
            RESET,
            json={"email": "mom@example.com", "email_verification_token": token, "new_password": password},
        )

        assert response.status_code == 422, password
        assert "new_password" in response.json()["error"]["fields"]
