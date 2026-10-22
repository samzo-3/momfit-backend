"""관리자 전용 API 접근 제어와 프로필의 role 노출."""

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from core.clock import utc_now
from models.user import ROLE_ADMIN, ROLE_USER, STATUS_WITHDRAWN, User
from tests.helpers import signup_payload

ADMIN_ME = "/api/admin/me"
ME = "/api/users/me"


def _signup(client: TestClient) -> str:
    response = client.post("/api/auth/signup", json=signup_payload())
    assert response.status_code == 201
    return response.json()["access_token"]


def _bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _make_admin(db: Session) -> None:
    db.get(User, 1).role = ROLE_ADMIN
    db.commit()


def test_가입한_사용자의_role은_user다(client: TestClient, db_session: Session) -> None:
    token = _signup(client)

    assert db_session.get(User, 1).role == ROLE_USER
    assert client.get(ME, headers=_bearer(token)).json()["role"] == "user"


def test_가입_요청으로_role을_지정할_수_없다(client: TestClient, db_session: Session) -> None:
    response = client.post("/api/auth/signup", json=signup_payload(role="admin"))

    assert response.status_code == 201
    assert db_session.get(User, 1).role == ROLE_USER


def test_프로필_수정으로_role을_바꿀_수_없다(client: TestClient, db_session: Session) -> None:
    token = _signup(client)

    response = client.patch(ME, json={"role": "admin"}, headers=_bearer(token))

    assert response.status_code == 422
    assert db_session.get(User, 1).role == ROLE_USER


def test_일반_사용자는_관리자_API가_403이다(client: TestClient) -> None:
    token = _signup(client)

    response = client.get(ADMIN_ME, headers=_bearer(token))

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "FORBIDDEN"


def test_관리자는_관리자_API를_호출할_수_있다(client: TestClient, db_session: Session) -> None:
    token = _signup(client)
    _make_admin(db_session)

    response = client.get(ADMIN_ME, headers=_bearer(token))

    assert response.status_code == 200
    assert response.json()["role"] == "admin"
    assert response.json()["nickname"] == "맘핏"


def test_토큰이_없으면_관리자_API가_401이다(client: TestClient) -> None:
    response = client.get(ADMIN_ME)

    assert response.status_code == 401


def test_탈퇴_유예_중인_관리자는_관리자_API를_쓸_수_없다(
    client: TestClient, db_session: Session
) -> None:
    token = _signup(client)
    _make_admin(db_session)
    # 관리자는 API로 탈퇴할 수 없으므로, 유예 상태가 된 경우를 DB에서 직접 만든다.
    user = db_session.get(User, 1)
    user.status = STATUS_WITHDRAWN
    user.withdrawn_at = utc_now()
    db_session.commit()

    response = client.get(ADMIN_ME, headers=_bearer(token))

    assert response.status_code == 401


def test_관리자는_탈퇴할_수_없다(client: TestClient, db_session: Session) -> None:
    token = _signup(client)
    _make_admin(db_session)

    response = client.delete(ME, headers=_bearer(token))

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "ADMIN_CANNOT_WITHDRAW"
    user = db_session.get(User, 1)
    assert user.status == "active"
    assert user.withdrawn_at is None
    # 거부됐으므로 로그인은 그대로 유지된다.
    assert client.get(ADMIN_ME, headers=_bearer(token)).status_code == 200
