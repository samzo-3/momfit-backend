from fastapi.testclient import TestClient

from tests.helpers import signup_payload


def _signup(client: TestClient) -> None:
    assert client.post("/api/auth/signup", json=signup_payload()).status_code == 201
    client.cookies.clear()


def _login(client: TestClient, login_id: str = "momfit01", password: str = "password1"):
    return client.post("/api/auth/login", json={"login_id": login_id, "password": password})


def test_로그인하면_access를_반환하고_refresh_쿠키를_설정한다(client: TestClient) -> None:
    _signup(client)

    response = _login(client)

    assert response.status_code == 200
    assert response.json()["access_token"]
    assert "refresh_token=" in response.headers["set-cookie"]


def test_아이디는_대소문자를_구분하지_않는다(client: TestClient) -> None:
    _signup(client)

    assert _login(client, login_id="  MomFit01 ").status_code == 200


def test_없는_아이디와_틀린_비밀번호는_같은_응답이다(client: TestClient) -> None:
    _signup(client)

    wrong_password = _login(client, password="wrong-pass1")
    unknown_user = _login(client, login_id="nobody01")

    assert wrong_password.status_code == unknown_user.status_code == 401
    assert wrong_password.json() == unknown_user.json()
    assert wrong_password.json()["error"]["code"] == "INVALID_CREDENTIALS"


def test_로그인_본문이_비어_있으면_422(client: TestClient) -> None:
    response = client.post("/api/auth/login", json={"login_id": "", "password": ""})

    assert response.status_code == 422
