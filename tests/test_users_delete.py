"""회원 탈퇴(소프트 딜리트): 계정은 지우지 않고 탈퇴 유예 상태로 바꾼다."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from models.auth_identity import AuthIdentity
from models.email_verification import EmailVerification
from models.refresh_token import RefreshToken
from models.user import STATUS_ACTIVE, STATUS_WITHDRAWN, User
from services.auth.kakao_client import KakaoError, KakaoNotConfigured
from tests.conftest import FakeKakaoClient, FakeMailer
from tests.helpers import kakao_login, signup_payload

ME = "/api/users/me"


def _signup(client: TestClient, **overrides) -> str:
    response = client.post("/api/auth/signup", json=signup_payload(**overrides))
    assert response.status_code == 201
    return response.json()["access_token"]


def _bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_탈퇴하면_204와_함께_refresh_쿠키를_삭제한다(client: TestClient) -> None:
    token = _signup(client)

    response = client.delete(ME, headers=_bearer(token))

    assert response.status_code == 204
    assert response.content == b""
    assert "Max-Age=0" in response.headers["set-cookie"]
    assert "Path=/api/auth" in response.headers["set-cookie"]


def test_계정은_지워지지_않고_탈퇴_유예_상태가_된다(
    client: TestClient, db_session: Session
) -> None:
    token = _signup(client)
    before = db_session.query(User).one()
    assert before.status == STATUS_ACTIVE
    assert before.withdrawn_at is None

    client.delete(ME, headers=_bearer(token))

    db_session.expire_all()
    user = db_session.query(User).one()
    assert user.status == STATUS_WITHDRAWN
    assert user.withdrawn_at is not None


def test_유예_기간에는_건강정보와_로그인_수단이_그대로_남는다(
    client: TestClient, db_session: Session
) -> None:
    token = _signup(client)
    due_date = db_session.query(User).one().due_date

    client.delete(ME, headers=_bearer(token))

    db_session.expire_all()
    user = db_session.query(User).one()
    assert user.due_date == due_date
    assert user.exercise_level == "low"
    assert user.email == "mom@example.com"
    assert db_session.query(AuthIdentity).count() == 1


def test_모든_refresh_토큰은_폐기된다(client: TestClient, db_session: Session) -> None:
    token = _signup(client)
    client.post(
        "/api/auth/login", json={"login_id": "momfit01", "password": "password1"}
    )
    assert db_session.query(RefreshToken).count() == 2

    client.delete(ME, headers=_bearer(token))

    db_session.expire_all()
    tokens = db_session.query(RefreshToken).all()
    assert len(tokens) == 2
    assert all(t.revoked_at is not None for t in tokens)


def test_이메일_인증_기록은_삭제_때까지_남는다(
    client: TestClient, db_session: Session, mailer: FakeMailer
) -> None:
    client.post(
        "/api/auth/email/send-code",
        json={"email": "mom@example.com", "purpose": "signup"},
    )
    token = _signup(client)

    client.delete(ME, headers=_bearer(token))

    db_session.expire_all()
    assert db_session.query(EmailVerification).count() == 1


def test_탈퇴한_뒤에는_기존_access_토큰이_거부된다(client: TestClient) -> None:
    token = _signup(client)
    client.delete(ME, headers=_bearer(token))

    response = client.get(ME, headers=_bearer(token))

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "UNAUTHORIZED"


def test_탈퇴한_뒤에는_기존_refresh_토큰으로_갱신할_수_없다(client: TestClient) -> None:
    token = _signup(client)
    refresh = client.cookies.get("refresh_token", path="/api/auth")
    client.delete(ME, headers=_bearer(token))

    client.cookies.set("refresh_token", refresh, path="/api/auth")
    refreshed = client.post("/api/auth/refresh")

    assert refreshed.status_code == 401
    assert refreshed.json()["error"]["code"] == "REFRESH_INVALID"


def test_탈퇴한_계정으로_로그인하면_403과_복구용_쿠키를_받는다(client: TestClient) -> None:
    token = _signup(client)
    client.delete(ME, headers=_bearer(token))
    client.cookies.clear()

    login = client.post(
        "/api/auth/login", json={"login_id": "momfit01", "password": "password1"}
    )

    assert login.status_code == 403
    assert login.json()["error"]["code"] == "ACCOUNT_WITHDRAWN"
    cookie = login.headers["set-cookie"]
    assert cookie.startswith("restore_token=")
    assert "HttpOnly" in cookie
    assert "Path=/api/auth" in cookie
    assert "Max-Age=600" in cookie
    # 로그인 토큰은 내려주지 않는다.
    assert "access_token" not in login.text
    assert client.cookies.get("refresh_token", path="/api/auth") is None


def test_탈퇴한_계정도_비밀번호가_틀리면_탈퇴_사실을_알려주지_않는다(
    client: TestClient,
) -> None:
    token = _signup(client)
    client.delete(ME, headers=_bearer(token))
    client.cookies.clear()

    login = client.post(
        "/api/auth/login", json={"login_id": "momfit01", "password": "wrong-password1"}
    )

    assert login.status_code == 401
    assert login.json()["error"]["code"] == "INVALID_CREDENTIALS"
    assert "restore_token" not in login.headers.get("set-cookie", "")


def test_유예_기간에는_같은_아이디와_이메일로_가입할_수_없다(client: TestClient) -> None:
    token = _signup(client)
    client.delete(ME, headers=_bearer(token))

    available = client.get("/api/auth/check-login-id", params={"login_id": "momfit01"})
    signup = client.post("/api/auth/signup", json=signup_payload())

    assert available.json() == {"available": False}
    assert signup.status_code == 409
    assert signup.json()["error"]["code"] == "LOGIN_ID_EXISTS"


def test_다른_사용자는_영향을_받지_않는다(client: TestClient, db_session: Session) -> None:
    first = _signup(client)
    second = _signup(client, login_id="momfit02", email="other@example.com")

    client.delete(ME, headers=_bearer(first))

    db_session.expire_all()
    statuses = {u.email: u.status for u in db_session.query(User).all()}
    assert statuses == {
        "mom@example.com": STATUS_WITHDRAWN,
        "other@example.com": STATUS_ACTIVE,
    }
    assert client.get(ME, headers=_bearer(second)).status_code == 200


def test_토큰이_없으면_401이고_아무것도_바뀌지_않는다(
    client: TestClient, db_session: Session
) -> None:
    _signup(client)

    response = client.delete(ME)

    assert response.status_code == 401
    assert db_session.query(User).one().status == STATUS_ACTIVE


class TestKakaoAccountWithdrawal:
    def _kakao_access(self, client: TestClient) -> str:
        kakao_login(client)
        return client.post("/api/auth/refresh").json()["access_token"]

    def test_카카오_계정을_탈퇴하면_연결을_끊고_계정은_유예_상태가_된다(
        self, client: TestClient, db_session: Session, kakao: FakeKakaoClient
    ) -> None:
        token = self._kakao_access(client)

        response = client.delete(ME, headers=_bearer(token))

        assert response.status_code == 204
        assert kakao.unlinked == ["12345"]
        db_session.expire_all()
        assert db_session.query(User).one().status == STATUS_WITHDRAWN
        assert db_session.query(AuthIdentity).count() == 1

    def test_연결_해제는_탈퇴_처리를_마친_뒤에_한다(
        self, client: TestClient, db_session: Session, kakao: FakeKakaoClient
    ) -> None:
        token = self._kakao_access(client)
        statuses_at_unlink: list[str] = []
        kakao.unlink = lambda _id: statuses_at_unlink.append(  # type: ignore[method-assign]
            db_session.query(User).one().status
        )

        client.delete(ME, headers=_bearer(token))

        assert statuses_at_unlink == [STATUS_WITHDRAWN]

    @pytest.mark.parametrize(
        "failure",
        [KakaoError("HTTP 500"), KakaoNotConfigured("설정 없음"), RuntimeError("예상 밖")],
    )
    def test_연결_해제에_실패해도_탈퇴는_완료된다(
        self,
        client: TestClient,
        db_session: Session,
        kakao: FakeKakaoClient,
        failure: Exception,
    ) -> None:
        token = self._kakao_access(client)
        kakao.fail_unlink = failure

        response = client.delete(ME, headers=_bearer(token))

        assert response.status_code == 204
        db_session.expire_all()
        assert db_session.query(User).one().status == STATUS_WITHDRAWN

    def test_탈퇴한_카카오_계정으로_다시_로그인하면_복구_화면으로_간다(
        self, client: TestClient, db_session: Session
    ) -> None:
        token = self._kakao_access(client)
        client.delete(ME, headers=_bearer(token))
        client.cookies.clear()

        response = kakao_login(client)

        assert response.status_code == 302
        assert response.headers["location"].endswith("/account/restore")
        assert any(
            h.startswith("restore_token=")
            for h in response.headers.get_list("set-cookie")
        )
        assert client.cookies.get("refresh_token", path="/api/auth") is None
        # 새 계정이 만들어지지 않는다.
        assert db_session.query(User).count() == 1

    def test_로컬_계정을_탈퇴해도_카카오를_호출하지_않는다(
        self, client: TestClient, kakao: FakeKakaoClient
    ) -> None:
        token = _signup(client)

        client.delete(ME, headers=_bearer(token))

        assert kakao.unlinked == []


def test_연결_해제_실패_원인을_로그에_남긴다(
    client: TestClient, kakao: FakeKakaoClient, caplog: pytest.LogCaptureFixture
) -> None:
    kakao_login(client)
    token = client.post("/api/auth/refresh").json()["access_token"]
    kakao.fail_unlink = KakaoError("카카오 API 오류 (HTTP 401)")

    with caplog.at_level("WARNING"):
        response = client.delete(ME, headers=_bearer(token))

    assert response.status_code == 204
    assert "카카오 연결 해제에 실패했습니다" in caplog.text
    assert "HTTP 401" in caplog.text
