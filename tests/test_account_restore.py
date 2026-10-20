"""탈퇴 유예 중인 계정의 복구."""

from datetime import timedelta

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from core.clock import utc_now
from core.config import settings
from core.security import create_access_token, create_restore_token
from models.user import STATUS_ACTIVE, STATUS_WITHDRAWN, User
from tests.helpers import kakao_login, signup_payload

ME = "/api/users/me"
RESTORE = "/api/auth/restore"


def _signup(client: TestClient, **overrides) -> str:
    response = client.post("/api/auth/signup", json=signup_payload(**overrides))
    assert response.status_code == 201
    return response.json()["access_token"]


def _bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _withdraw_and_login(client: TestClient) -> None:
    """가입 → 탈퇴 → 로그인 시도까지 해서 복구용 쿠키를 받은 상태로 만든다."""
    token = _signup(client)
    client.delete(ME, headers=_bearer(token))
    client.cookies.clear()
    login = client.post(
        "/api/auth/login", json={"login_id": "momfit01", "password": "password1"}
    )
    assert login.status_code == 403


def test_복구_정보로_탈퇴_시각과_삭제_예정_시각을_알려준다(
    client: TestClient, db_session: Session
) -> None:
    _withdraw_and_login(client)

    response = client.get(RESTORE)

    assert response.status_code == 200
    body = response.json()
    withdrawn_at = db_session.query(User).one().withdrawn_at
    assert body["withdrawn_at"].startswith(withdrawn_at.isoformat()[:19])
    assert body["withdrawn_at"].endswith("Z") or body["withdrawn_at"].endswith("+00:00")
    # 삭제 예정은 탈퇴 시각에서 유예 기간(기본 30일) 뒤다.
    assert body["purge_at"].startswith(
        (withdrawn_at + timedelta(days=settings.account_grace_days)).isoformat()[:19]
    )


def test_복구하면_다시_이용할_수_있고_토큰을_받는다(
    client: TestClient, db_session: Session
) -> None:
    _withdraw_and_login(client)

    response = client.post(RESTORE)

    assert response.status_code == 200
    token = response.json()["access_token"]
    assert response.json()["token_type"] == "bearer"
    assert client.cookies.get("refresh_token", path="/api/auth") is not None
    db_session.expire_all()
    user = db_session.query(User).one()
    assert user.status == STATUS_ACTIVE
    assert user.withdrawn_at is None
    assert client.get(ME, headers=_bearer(token)).status_code == 200


def test_복구하면_복구용_쿠키는_삭제되고_다시_쓸_수_없다(client: TestClient) -> None:
    _withdraw_and_login(client)

    response = client.post(RESTORE)

    assert any(
        h.startswith("restore_token=") and "Max-Age=0" in h
        for h in response.headers.get_list("set-cookie")
    )
    again = client.post(RESTORE)
    assert again.status_code == 401
    assert again.json()["error"]["code"] == "RESTORE_INVALID"


def test_복구한_뒤에는_평소처럼_로그인할_수_있다(client: TestClient) -> None:
    _withdraw_and_login(client)
    client.post(RESTORE)
    client.cookies.clear()

    login = client.post(
        "/api/auth/login", json={"login_id": "momfit01", "password": "password1"}
    )

    assert login.status_code == 200


def test_복구한_계정은_다시_탈퇴할_수_있고_새_유예_기간이_시작된다(
    client: TestClient, db_session: Session
) -> None:
    _withdraw_and_login(client)
    token = client.post(RESTORE).json()["access_token"]

    client.delete(ME, headers=_bearer(token))

    db_session.expire_all()
    user = db_session.query(User).one()
    assert user.status == STATUS_WITHDRAWN
    assert utc_now() - user.withdrawn_at < timedelta(minutes=1)


def test_복구용_쿠키가_없으면_401이다(client: TestClient) -> None:
    for call in (client.get, client.post):
        response = call(RESTORE)

        assert response.status_code == 401
        assert response.json()["error"]["code"] == "RESTORE_INVALID"


def test_복구_토큰이_잘못되거나_만료되면_401이다(client: TestClient) -> None:
    _withdraw_and_login(client)
    client.cookies.set("restore_token", "not-a-token", path="/api/auth")

    response = client.post(RESTORE)

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "RESTORE_INVALID"


def test_access_토큰으로는_복구할_수_없다(
    client: TestClient, db_session: Session
) -> None:
    _withdraw_and_login(client)
    user = db_session.query(User).one()
    client.cookies.set("restore_token", create_access_token(user.id), path="/api/auth")

    response = client.post(RESTORE)

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "RESTORE_INVALID"


def test_복구_토큰으로는_일반_API를_쓸_수_없다(
    client: TestClient, db_session: Session
) -> None:
    _withdraw_and_login(client)
    user = db_session.query(User).one()

    response = client.get(ME, headers=_bearer(create_restore_token(user.id)))

    assert response.status_code == 401


def test_이용_중인_계정은_복구_토큰이_있어도_복구_대상이_아니다(
    client: TestClient, db_session: Session
) -> None:
    _signup(client)
    user = db_session.query(User).one()
    client.cookies.set("restore_token", create_restore_token(user.id), path="/api/auth")

    for call in (client.get, client.post):
        response = call(RESTORE)

        assert response.status_code == 401
        assert response.json()["error"]["code"] == "RESTORE_INVALID"


def test_유예_기간이_지나면_삭제_전이라도_복구할_수_없다(
    client: TestClient, db_session: Session
) -> None:
    _withdraw_and_login(client)
    user = db_session.query(User).one()
    user.withdrawn_at = utc_now() - timedelta(days=settings.account_grace_days, seconds=1)
    db_session.commit()

    for call in (client.get, client.post):
        response = call(RESTORE)

        assert response.status_code == 401
        assert response.json()["error"]["code"] == "RESTORE_INVALID"
    db_session.expire_all()
    assert db_session.query(User).one().status == STATUS_WITHDRAWN


def test_삭제되고_없는_계정의_복구_토큰은_거부한다(
    client: TestClient, db_session: Session
) -> None:
    client.cookies.set("restore_token", create_restore_token(9999), path="/api/auth")

    response = client.post(RESTORE)

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "RESTORE_INVALID"


class TestKakaoRestore:
    def _withdraw_kakao_and_login(self, client: TestClient) -> None:
        kakao_login(client)
        token = client.post("/api/auth/refresh").json()["access_token"]
        client.delete(ME, headers=_bearer(token))
        client.cookies.clear()
        response = kakao_login(client)
        assert response.headers["location"].endswith("/account/restore")

    def test_카카오_계정도_복구할_수_있다(
        self, client: TestClient, db_session: Session
    ) -> None:
        self._withdraw_kakao_and_login(client)

        response = client.post(RESTORE)

        assert response.status_code == 200
        db_session.expire_all()
        assert db_session.query(User).one().status == STATUS_ACTIVE
        me = client.get(ME, headers=_bearer(response.json()["access_token"]))
        assert me.status_code == 200
        assert me.json()["provider"] == "kakao"

    def test_복구하지_않으면_계속_탈퇴_상태다(
        self, client: TestClient, db_session: Session
    ) -> None:
        self._withdraw_kakao_and_login(client)
        client.cookies.clear()

        again = kakao_login(client)

        assert again.headers["location"].endswith("/account/restore")
        db_session.expire_all()
        assert db_session.query(User).one().status == STATUS_WITHDRAWN


def test_복구_API는_로그인_토큰_없이_호출할_수_있는_공개_경로다(client: TestClient) -> None:
    # 복구용 쿠키가 없을 뿐 인증 헤더 때문에 막히지는 않는다. (UNAUTHORIZED가 아니라 RESTORE_INVALID)
    response = client.post(RESTORE)

    assert response.json()["error"]["code"] == "RESTORE_INVALID"
