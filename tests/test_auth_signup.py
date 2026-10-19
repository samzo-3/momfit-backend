from datetime import timedelta

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from core.clock import today_kst
from core.security import create_email_verification_token
from models.auth_identity import AuthIdentity
from models.user import User
from tests.helpers import signup_payload


def test_가입하면_access를_반환하고_refresh_쿠키를_설정한다(client: TestClient) -> None:
    response = client.post("/api/auth/signup", json=signup_payload())

    assert response.status_code == 201
    body = response.json()
    assert body["token_type"] == "bearer"
    assert body["expires_in"] == 900
    assert body["access_token"]
    cookie = response.headers["set-cookie"]
    assert "refresh_token=" in cookie
    assert "HttpOnly" in cookie
    assert "SameSite=lax" in cookie
    assert "Path=/api/auth" in cookie


def test_운영_설정에서는_쿠키에_Secure가_붙는다(
    client: TestClient, monkeypatch
) -> None:
    from dataclasses import replace

    import api.auth

    monkeypatch.setattr(api.auth, "settings", replace(api.auth.settings, cookie_secure=True))

    response = client.post("/api/auth/signup", json=signup_payload())

    assert "Secure" in response.headers["set-cookie"]


def test_가입한_사용자의_프로필이_저장된다(client: TestClient, db_session: Session) -> None:
    client.post("/api/auth/signup", json=signup_payload())

    user = db_session.query(User).one()
    identity = db_session.query(AuthIdentity).one()
    assert user.nickname == "맘핏"
    assert user.email == "mom@example.com"
    assert user.onboarding_completed is True
    assert user.terms_agreed_at is not None
    assert identity.provider == "local"
    assert identity.login_id == "momfit01"
    assert identity.password_hash != "password1"
    assert identity.password_hash.startswith("$argon2")


def test_이메일은_소문자로_정규화되어_저장된다(
    client: TestClient, db_session: Session
) -> None:
    token = create_email_verification_token("mom@example.com", "signup")

    response = client.post(
        "/api/auth/signup",
        json=signup_payload(email=" Mom@Example.com ", email_verification_token=token),
    )

    assert response.status_code == 201
    assert db_session.query(User).one().email == "mom@example.com"


def test_중복_아이디는_409(client: TestClient) -> None:
    client.post("/api/auth/signup", json=signup_payload())

    response = client.post(
        "/api/auth/signup", json=signup_payload(email="other@example.com")
    )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "LOGIN_ID_EXISTS"


def test_중복_이메일은_409(client: TestClient) -> None:
    client.post("/api/auth/signup", json=signup_payload())

    response = client.post(
        "/api/auth/signup", json=signup_payload(login_id="momfit02")
    )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "EMAIL_EXISTS"


def test_인증된_이메일과_요청_이메일이_다르면_EMAIL_TOKEN_INVALID(
    client: TestClient,
) -> None:
    token = create_email_verification_token("someone@example.com", "signup")

    response = client.post(
        "/api/auth/signup",
        json=signup_payload(email="mom@example.com", email_verification_token=token),
    )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "EMAIL_TOKEN_INVALID"


def test_비밀번호_재설정용_토큰으로는_가입할_수_없다(client: TestClient) -> None:
    token = create_email_verification_token("mom@example.com", "password_reset")

    response = client.post(
        "/api/auth/signup", json=signup_payload(email_verification_token=token)
    )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "EMAIL_TOKEN_INVALID"


def test_약관에_동의하지_않으면_422(client: TestClient) -> None:
    response = client.post(
        "/api/auth/signup",
        json=signup_payload(consents={"terms": True, "health_data": False}),
    )

    assert response.status_code == 422
    assert "consents.health_data" in response.json()["error"]["fields"]


def test_비밀번호_규칙_위반은_422(client: TestClient) -> None:
    for password in ("short1", "onlyletters", "12345678"):
        response = client.post("/api/auth/signup", json=signup_payload(password=password))

        assert response.status_code == 422, password
        assert "password" in response.json()["error"]["fields"]


def test_아이디_형식_위반은_422(client: TestClient) -> None:
    for login_id in ("abc", "UPPER01", "has space1", "a" * 21):
        response = client.post("/api/auth/signup", json=signup_payload(login_id=login_id))

        assert response.status_code == 422, login_id
        assert "login_id" in response.json()["error"]["fields"]


def test_출산_예정일이_범위를_벗어나면_422(client: TestClient) -> None:
    for offset in (-1, 281):
        due = (today_kst() + timedelta(days=offset)).isoformat()
        response = client.post("/api/auth/signup", json=signup_payload(due_date=due))

        assert response.status_code == 422, offset
        assert "due_date" in response.json()["error"]["fields"]


def test_운동_경험은_정해진_값만_허용한다(client: TestClient) -> None:
    response = client.post(
        "/api/auth/signup", json=signup_payload(exercise_level="expert")
    )

    assert response.status_code == 422
    assert "exercise_level" in response.json()["error"]["fields"]


def test_아이디_중복_확인(client: TestClient) -> None:
    assert client.get("/api/auth/check-login-id", params={"login_id": "momfit01"}).json() == {
        "available": True
    }

    client.post("/api/auth/signup", json=signup_payload())

    for login_id in ("momfit01", "MOMFIT01"):
        response = client.get("/api/auth/check-login-id", params={"login_id": login_id})
        assert response.json() == {"available": False}
