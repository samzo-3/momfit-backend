from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from core.clock import today_kst
from core.security import create_access_token
from models.user import User
from tests.helpers import signup_payload

ME = "/api/users/me"


def _signup_token(client: TestClient) -> str:
    response = client.post("/api/auth/signup", json=signup_payload())
    assert response.status_code == 201
    return response.json()["access_token"]


def _bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _due(days: int) -> str:
    return (today_kst() + timedelta(days=days)).isoformat()


def test_닉네임만_수정하면_나머지는_그대로다(client: TestClient) -> None:
    token = _signup_token(client)
    before = client.get(ME, headers=_bearer(token)).json()

    response = client.patch(ME, headers=_bearer(token), json={"nickname": "새닉네임"})

    assert response.status_code == 200
    assert response.json() == {**before, "nickname": "새닉네임"}


def test_세_필드를_함께_수정한다(client: TestClient) -> None:
    token = _signup_token(client)

    response = client.patch(
        ME,
        headers=_bearer(token),
        json={"nickname": "  둘째맘 ", "due_date": _due(56), "exercise_level": "high"},
    )

    body = response.json()
    assert response.status_code == 200
    assert body["nickname"] == "둘째맘"
    assert body["due_date"] == _due(56)
    assert body["exercise_level"] == "high"


def test_출산_예정일을_바꾸면_임신_주차를_다시_계산한다(client: TestClient) -> None:
    token = _signup_token(client)  # 가입 시 예정일은 84일 뒤 → 28주

    response = client.patch(ME, headers=_bearer(token), json={"due_date": _due(7)})

    assert response.json()["pregnancy_week"] == 39


def test_수정한_값이_저장된다(client: TestClient, db_session: Session) -> None:
    token = _signup_token(client)

    client.patch(ME, headers=_bearer(token), json={"exercise_level": "medium"})

    db_session.expire_all()
    assert db_session.get(User, 1).exercise_level == "medium"
    assert client.get(ME, headers=_bearer(token)).json()["exercise_level"] == "medium"


@pytest.mark.parametrize("offset", [-1, 281])
def test_범위를_벗어난_출산_예정일은_422(client: TestClient, offset: int) -> None:
    token = _signup_token(client)

    response = client.patch(ME, headers=_bearer(token), json={"due_date": _due(offset)})

    assert response.status_code == 422
    assert "due_date" in response.json()["error"]["fields"]


@pytest.mark.parametrize(
    ("body", "field"),
    [
        ({"nickname": ""}, "nickname"),
        ({"nickname": "   "}, "nickname"),
        ({"nickname": "가" * 21}, "nickname"),
        ({"exercise_level": "expert"}, "exercise_level"),
        ({"due_date": "not-a-date"}, "due_date"),
    ],
)
def test_잘못된_값은_422(client: TestClient, body: dict, field: str) -> None:
    token = _signup_token(client)

    response = client.patch(ME, headers=_bearer(token), json=body)

    assert response.status_code == 422
    assert field in response.json()["error"]["fields"]


def test_빈_본문은_422(client: TestClient) -> None:
    token = _signup_token(client)

    response = client.patch(ME, headers=_bearer(token), json={})

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


@pytest.mark.parametrize("field", ["nickname", "due_date", "exercise_level"])
def test_null로는_바꿀_수_없다(client: TestClient, field: str) -> None:
    token = _signup_token(client)

    response = client.patch(ME, headers=_bearer(token), json={field: None})

    assert response.status_code == 422


@pytest.mark.parametrize(
    "field", ["email", "login_id", "id", "provider", "onboarding_completed", "pregnancy_week"]
)
def test_바꿀_수_없는_필드를_보내면_422이고_값은_그대로다(
    client: TestClient, db_session: Session, field: str
) -> None:
    token = _signup_token(client)
    before = client.get(ME, headers=_bearer(token)).json()

    response = client.patch(ME, headers=_bearer(token), json={field: "hacked"})

    assert response.status_code == 422
    assert client.get(ME, headers=_bearer(token)).json() == before


def test_토큰이_없으면_401(client: TestClient) -> None:
    response = client.patch(ME, json={"nickname": "x"})

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "UNAUTHORIZED"


def test_다른_사용자의_정보는_바뀌지_않는다(client: TestClient, db_session: Session) -> None:
    first = _signup_token(client)
    second = client.post(
        "/api/auth/signup",
        json=signup_payload(login_id="momfit02", email="other@example.com"),
    ).json()["access_token"]

    client.patch(ME, headers=_bearer(second), json={"nickname": "두번째"})

    assert client.get(ME, headers=_bearer(first)).json()["nickname"] == "맘핏"
    assert client.get(ME, headers=_bearer(second)).json()["nickname"] == "두번째"


def test_존재하지_않는_사용자의_토큰은_401(client: TestClient) -> None:
    response = client.patch(
        ME, headers=_bearer(create_access_token(999)), json={"nickname": "x"}
    )

    assert response.status_code == 401
