from datetime import timedelta

from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from api.deps import get_onboarded_user
from core.clock import today_kst
from core.errors import register_exception_handlers
from core.security import create_access_token
from db.session import get_db
from models.user import User
from tests.helpers import signup_payload


def _signup_token(client: TestClient, **overrides) -> str:
    response = client.post("/api/auth/signup", json=signup_payload(**overrides))
    assert response.status_code == 201
    return response.json()["access_token"]


def _bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_내_정보를_조회한다(client: TestClient) -> None:
    due_date = today_kst() + timedelta(days=84)  # 임신 28주 0일
    token = _signup_token(client, due_date=due_date.isoformat())

    response = client.get("/api/users/me", headers=_bearer(token))

    assert response.status_code == 200
    assert response.json() == {
        "id": 1,
        "provider": "local",
        "login_id": "momfit01",
        "nickname": "맘핏",
        "email": "mom@example.com",
        "due_date": due_date.isoformat(),
        "pregnancy_week": 28,
        "exercise_level": "low",
        "onboarding_completed": True,
        "role": "user",
    }


def test_토큰이_없으면_401_UNAUTHORIZED(client: TestClient) -> None:
    response = client.get("/api/users/me")

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "UNAUTHORIZED"


def test_Bearer가_아닌_스킴은_401(client: TestClient) -> None:
    response = client.get("/api/users/me", headers={"Authorization": "Basic abc"})

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "UNAUTHORIZED"


def test_만료된_토큰은_401_TOKEN_EXPIRED(client: TestClient) -> None:
    _signup_token(client)
    expired = create_access_token(1, expires_delta=timedelta(seconds=-1))

    response = client.get("/api/users/me", headers=_bearer(expired))

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "TOKEN_EXPIRED"


def test_존재하지_않는_사용자의_토큰은_401(client: TestClient) -> None:
    response = client.get("/api/users/me", headers=_bearer(create_access_token(999)))

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "UNAUTHORIZED"


def test_온보딩이_끝나지_않은_사용자는_ONBOARDING_REQUIRED(
    client: TestClient, db_session: Session
) -> None:
    token = _signup_token(client)
    db_session.get(User, 1).onboarding_completed = False
    db_session.commit()

    # 전역 앱을 오염시키지 않도록 보호 라우트만 가진 별도 앱으로 검증한다.
    test_app = FastAPI()
    register_exception_handlers(test_app)
    test_app.dependency_overrides[get_db] = lambda: db_session

    @test_app.get("/protected")
    def protected(user: User = Depends(get_onboarded_user)) -> dict[str, int]:
        return {"id": user.id}

    # /users/me는 온보딩 전에도 접근할 수 있다.
    assert client.get("/api/users/me", headers=_bearer(token)).status_code == 200
    response = TestClient(test_app).get("/protected", headers=_bearer(token))

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "ONBOARDING_REQUIRED"
