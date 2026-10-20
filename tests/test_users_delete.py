import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from models.auth_identity import AuthIdentity
from models.email_verification import EmailVerification
from models.refresh_token import RefreshToken
from models.user import User
from services.kakao_client import KakaoError, KakaoNotConfigured
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


def test_사용자와_로그인_수단과_토큰이_모두_삭제된다(
    client: TestClient, db_session: Session
) -> None:
    token = _signup(client)

    client.delete(ME, headers=_bearer(token))

    db_session.expire_all()
    assert db_session.query(User).count() == 0
    assert db_session.query(AuthIdentity).count() == 0
    assert db_session.query(RefreshToken).count() == 0


def test_이메일_인증_기록도_삭제된다(
    client: TestClient, db_session: Session, mailer: FakeMailer
) -> None:
    client.post(
        "/api/auth/email/send-code",
        json={"email": "mom@example.com", "purpose": "signup"},
    )
    token = _signup(client)
    assert db_session.query(EmailVerification).count() == 1

    client.delete(ME, headers=_bearer(token))

    db_session.expire_all()
    assert db_session.query(EmailVerification).count() == 0


def test_탈퇴한_뒤에는_기존_access_토큰이_거부된다(client: TestClient) -> None:
    token = _signup(client)
    client.delete(ME, headers=_bearer(token))

    response = client.get(ME, headers=_bearer(token))

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "UNAUTHORIZED"


def test_탈퇴한_뒤에는_로그인과_토큰_갱신이_안_된다(client: TestClient) -> None:
    token = _signup(client)
    refresh = client.cookies.get("refresh_token", path="/api/auth")
    client.delete(ME, headers=_bearer(token))

    login = client.post(
        "/api/auth/login", json={"login_id": "momfit01", "password": "password1"}
    )
    client.cookies.set("refresh_token", refresh, path="/api/auth")
    refreshed = client.post("/api/auth/refresh")

    assert login.status_code == 401
    assert login.json()["error"]["code"] == "INVALID_CREDENTIALS"
    assert refreshed.status_code == 401
    assert refreshed.json()["error"]["code"] == "REFRESH_INVALID"


def test_탈퇴한_아이디와_이메일로_다시_가입할_수_있다(client: TestClient) -> None:
    token = _signup(client)
    client.delete(ME, headers=_bearer(token))

    response = client.post("/api/auth/signup", json=signup_payload())

    assert response.status_code == 201


def test_다른_사용자의_데이터는_남는다(client: TestClient, db_session: Session) -> None:
    first = _signup(client)
    second = _signup(client, login_id="momfit02", email="other@example.com")

    client.delete(ME, headers=_bearer(first))

    db_session.expire_all()
    assert [u.email for u in db_session.query(User).all()] == ["other@example.com"]
    assert db_session.query(AuthIdentity).count() == 1
    assert client.get(ME, headers=_bearer(second)).status_code == 200


def test_토큰이_없으면_401이고_아무것도_삭제되지_않는다(
    client: TestClient, db_session: Session
) -> None:
    _signup(client)

    response = client.delete(ME)

    assert response.status_code == 401
    assert db_session.query(User).count() == 1


class TestKakaoAccountDeletion:
    def _kakao_access(self, client: TestClient) -> str:
        kakao_login(client)
        return client.post("/api/auth/refresh").json()["access_token"]

    def test_카카오_계정을_탈퇴하면_연결도_끊는다(
        self, client: TestClient, db_session: Session, kakao: FakeKakaoClient
    ) -> None:
        token = self._kakao_access(client)

        response = client.delete(ME, headers=_bearer(token))

        assert response.status_code == 204
        assert kakao.unlinked == ["12345"]
        db_session.expire_all()
        assert db_session.query(User).count() == 0
        assert db_session.query(AuthIdentity).count() == 0
        assert db_session.query(RefreshToken).count() == 0

    def test_연결_해제는_삭제가_끝난_뒤에_한다(
        self, client: TestClient, db_session: Session, kakao: FakeKakaoClient
    ) -> None:
        token = self._kakao_access(client)
        users_at_unlink: list[int] = []
        kakao.unlink = lambda _id: users_at_unlink.append(  # type: ignore[method-assign]
            db_session.query(User).count()
        )

        client.delete(ME, headers=_bearer(token))

        assert users_at_unlink == [0]

    @pytest.mark.parametrize("failure", [KakaoError("HTTP 500"), KakaoNotConfigured("설정 없음"), RuntimeError("예상 밖")])
    def test_연결_해제에_실패해도_탈퇴는_완료된다(
        self, client: TestClient, db_session: Session, kakao: FakeKakaoClient, failure: Exception
    ) -> None:
        token = self._kakao_access(client)
        kakao.fail_unlink = failure

        response = client.delete(ME, headers=_bearer(token))

        assert response.status_code == 204
        db_session.expire_all()
        assert db_session.query(User).count() == 0

    def test_탈퇴한_카카오_계정으로_다시_로그인하면_새_계정이_된다(
        self, client: TestClient, db_session: Session
    ) -> None:
        token = self._kakao_access(client)
        client.delete(ME, headers=_bearer(token))
        client.cookies.clear()

        kakao_login(client)

        assert db_session.query(User).count() == 1
        me = client.post("/api/auth/refresh").json()["access_token"]
        profile = client.get(ME, headers=_bearer(me)).json()
        assert profile["onboarding_completed"] is False

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
