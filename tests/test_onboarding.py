from datetime import timedelta

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from api.deps import get_onboarded_user
from core.clock import today_kst
from core.errors import register_exception_handlers
from db.session import get_db
from models.user import User
from tests.helpers import kakao_login, signup_payload

ME = "/api/users/me"
ONBOARDING = "/api/users/me/onboarding"


def _due(days: int) -> str:
    return (today_kst() + timedelta(days=days)).isoformat()


def _payload(**overrides) -> dict:
    payload = {
        "nickname": "카카오맘",
        "due_date": _due(84),
        "exercise_level": "medium",
        "consents": {"terms": True, "health_data": True},
    }
    payload.update(overrides)
    return payload


def _kakao_token(client: TestClient) -> str:
    kakao_login(client)
    return client.post("/api/auth/refresh").json()["access_token"]


def _bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_카카오_가입자가_제출하면_온보딩이_완료되고_프로필이_채워진다(
    client: TestClient, db_session: Session
) -> None:
    token = _kakao_token(client)

    response = client.post(ONBOARDING, headers=_bearer(token), json=_payload(nickname="  새닉네임 "))

    assert response.status_code == 200
    assert response.json() == {
        "id": 1,
        "provider": "kakao",
        "login_id": None,
        "nickname": "새닉네임",
        "email": None,
        "due_date": _due(84),
        "pregnancy_week": 28,
        "exercise_level": "medium",
        "onboarding_completed": True,
        "role": "user",
    }
    db_session.expire_all()
    user = db_session.get(User, 1)
    assert user.terms_agreed_at is not None
    assert user.health_data_agreed_at is not None


def test_온보딩_전에도_내_정보는_조회할_수_있다(client: TestClient) -> None:
    token = _kakao_token(client)

    response = client.get(ME, headers=_bearer(token))

    assert response.status_code == 200
    assert response.json()["onboarding_completed"] is False


def test_온보딩이_끝난_뒤_내_정보에도_반영된다(client: TestClient) -> None:
    token = _kakao_token(client)
    client.post(ONBOARDING, headers=_bearer(token), json=_payload())

    me = client.get(ME, headers=_bearer(token)).json()

    assert me["onboarding_completed"] is True
    assert me["exercise_level"] == "medium"


def test_두_번_제출하면_409(client: TestClient) -> None:
    token = _kakao_token(client)
    client.post(ONBOARDING, headers=_bearer(token), json=_payload())

    response = client.post(ONBOARDING, headers=_bearer(token), json=_payload(nickname="바꿈"))

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "ONBOARDING_ALREADY_COMPLETED"
    assert client.get(ME, headers=_bearer(token)).json()["nickname"] == "카카오맘"


def test_가입을_마친_로컬_계정은_409(client: TestClient) -> None:
    token = client.post("/api/auth/signup", json=signup_payload()).json()["access_token"]

    response = client.post(ONBOARDING, headers=_bearer(token), json=_payload())

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "ONBOARDING_ALREADY_COMPLETED"


def test_토큰이_없으면_401(client: TestClient) -> None:
    response = client.post(ONBOARDING, json=_payload())

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "UNAUTHORIZED"


@pytest.mark.parametrize(
    ("consents", "field"),
    [
        ({"terms": True, "health_data": False}, "consents.health_data"),
        ({"terms": False, "health_data": True}, "consents.health_data"),
        ({"terms": False, "health_data": False}, "consents.health_data"),
    ],
)
def test_두_가지_동의가_모두_필요하다(
    client: TestClient, db_session: Session, consents: dict, field: str
) -> None:
    token = _kakao_token(client)

    response = client.post(ONBOARDING, headers=_bearer(token), json=_payload(consents=consents))

    assert response.status_code == 422
    assert field in response.json()["error"]["fields"]
    db_session.expire_all()
    assert db_session.get(User, 1).onboarding_completed is False


@pytest.mark.parametrize(
    ("overrides", "field"),
    [
        ({"nickname": ""}, "nickname"),
        ({"nickname": "   "}, "nickname"),
        ({"nickname": "가" * 21}, "nickname"),
        ({"exercise_level": "expert"}, "exercise_level"),
        ({"due_date": "not-a-date"}, "due_date"),
        ({"due_date": _due(-1)}, "due_date"),
        ({"due_date": _due(281)}, "due_date"),
    ],
)
def test_잘못된_값은_422이고_온보딩은_완료되지_않는다(
    client: TestClient, db_session: Session, overrides: dict, field: str
) -> None:
    token = _kakao_token(client)

    response = client.post(ONBOARDING, headers=_bearer(token), json=_payload(**overrides))

    assert response.status_code == 422
    assert field in response.json()["error"]["fields"]
    db_session.expire_all()
    user = db_session.get(User, 1)
    assert user.onboarding_completed is False
    assert user.due_date is None


@pytest.mark.parametrize("missing", ["nickname", "due_date", "exercise_level", "consents"])
def test_필수_항목이_빠지면_422(client: TestClient, missing: str) -> None:
    token = _kakao_token(client)
    payload = _payload()
    del payload[missing]

    response = client.post(ONBOARDING, headers=_bearer(token), json=payload)

    assert response.status_code == 422
    assert missing in response.json()["error"]["fields"]


def test_정해진_항목_외에는_보낼_수_없다(client: TestClient) -> None:
    token = _kakao_token(client)

    response = client.post(
        ONBOARDING, headers=_bearer(token), json=_payload(onboarding_completed=True, email="a@b.com")
    )

    assert response.status_code == 422


def test_온보딩_전_사용자는_보호_API에서_ONBOARDING_REQUIRED(
    client: TestClient, db_session: Session
) -> None:
    token = _kakao_token(client)
    # 온보딩을 마쳐야만 쓰는 API를 흉내 내는 별도 앱 (전역 앱을 오염시키지 않는다)
    test_app = FastAPI()
    register_exception_handlers(test_app)
    test_app.dependency_overrides[get_db] = lambda: db_session

    @test_app.get("/protected")
    def protected(user: User = Depends(get_onboarded_user)) -> dict[str, int]:
        return {"id": user.id}

    other = TestClient(test_app)

    before = other.get("/protected", headers=_bearer(token))
    client.post(ONBOARDING, headers=_bearer(token), json=_payload())
    after = other.get("/protected", headers=_bearer(token))

    assert before.status_code == 403
    assert before.json()["error"]["code"] == "ONBOARDING_REQUIRED"
    assert after.status_code == 200
