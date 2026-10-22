from dataclasses import replace

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

import api.kakao_auth
from models.auth_identity import AuthIdentity
from models.refresh_token import RefreshToken
from models.user import User
from services.auth.kakao_client import KakaoError, KakaoNotConfigured, KakaoProfile
from tests.conftest import FakeKakaoClient
from tests.helpers import kakao_login

LOGIN = "/api/auth/kakao/login"
CALLBACK = "/api/auth/kakao/callback"


def _state_of(location: str) -> str:
    return location.split("state=")[1].split("&")[0]


class TestKakaoLoginStart:
    def test_카카오_인가_페이지로_302로_보낸다(self, client: TestClient) -> None:
        response = client.get(LOGIN, follow_redirects=False)

        assert response.status_code == 302
        assert response.headers["location"].startswith(
            "https://kauth.kakao.com/oauth/authorize?"
        )

    def test_state를_만들어_쿠키와_주소에_같은_값으로_담는다(self, client: TestClient) -> None:
        response = client.get(LOGIN, follow_redirects=False)

        state = _state_of(response.headers["location"])
        assert len(state) >= 32
        assert client.cookies.get("kakao_state", path="/api/auth/kakao") == state

    def test_state_쿠키는_httpOnly이고_경로와_수명이_제한된다(self, client: TestClient) -> None:
        response = client.get(LOGIN, follow_redirects=False)

        cookie = response.headers["set-cookie"]
        assert "HttpOnly" in cookie
        assert "SameSite=lax" in cookie
        assert "Path=/api/auth/kakao" in cookie
        assert "Max-Age=600" in cookie

    def test_운영_설정에서는_state_쿠키에_Secure가_붙는다(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(
            api.kakao_auth, "settings", replace(api.kakao_auth.settings, cookie_secure=True)
        )

        response = client.get(LOGIN, follow_redirects=False)

        assert "Secure" in response.headers["set-cookie"]

    def test_요청마다_다른_state를_쓴다(self, client: TestClient) -> None:
        first = _state_of(client.get(LOGIN, follow_redirects=False).headers["location"])
        second = _state_of(client.get(LOGIN, follow_redirects=False).headers["location"])

        assert first != second

    def test_설정이_없으면_로그인_화면으로_오류와_함께_보낸다(
        self, client: TestClient, kakao: FakeKakaoClient
    ) -> None:
        kakao.fail_authorize = KakaoNotConfigured("설정 없음")

        response = client.get(LOGIN, follow_redirects=False)

        assert response.status_code == 302
        assert response.headers["location"] == "/login?error=provider_error"
        assert "refresh_token=" not in response.headers.get("set-cookie", "")


class TestKakaoCallbackSuccess:
    def test_처음_로그인하면_온보딩_전_계정을_만들고_프론트로_보낸다(
        self, client: TestClient, db_session: Session, kakao: FakeKakaoClient
    ) -> None:
        response = kakao_login(client)

        assert response.status_code == 302
        assert response.headers["location"] == "/auth/callback"
        user = db_session.query(User).one()
        assert user.nickname == "카카오맘"
        assert user.onboarding_completed is False
        assert user.email is None
        assert user.due_date is None
        assert user.terms_agreed_at is None
        assert kakao.exchanged_codes == ["auth-code"]

    def test_로그인_수단은_회원번호만_저장한다(
        self, client: TestClient, db_session: Session
    ) -> None:
        kakao_login(client)

        identity = db_session.query(AuthIdentity).one()
        assert identity.provider == "kakao"
        assert identity.provider_user_id == "12345"
        assert identity.login_id is None
        assert identity.password_hash is None

    def test_refresh_쿠키를_설정하고_state_쿠키를_지운다(self, client: TestClient) -> None:
        response = kakao_login(client)

        cookies = response.headers.get_list("set-cookie")
        refresh = next(c for c in cookies if c.startswith("refresh_token="))
        state = next(c for c in cookies if c.startswith("kakao_state="))
        assert "HttpOnly" in refresh and "Path=/api/auth" in refresh
        assert "Max-Age=0" in state

    def test_발급된_refresh로_세션을_받고_내_정보를_조회한다(self, client: TestClient) -> None:
        kakao_login(client)

        access = client.post("/api/auth/refresh").json()["access_token"]
        me = client.get("/api/users/me", headers={"Authorization": f"Bearer {access}"})

        assert me.status_code == 200
        assert me.json() == {
            "id": 1,
            "provider": "kakao",
            "login_id": None,
            "nickname": "카카오맘",
            "email": None,
            "due_date": None,
            "pregnancy_week": None,
            "exercise_level": None,
            "onboarding_completed": False,
            "role": "user",
        }

    def test_다시_로그인하면_같은_계정으로_로그인한다(
        self, client: TestClient, db_session: Session
    ) -> None:
        kakao_login(client)
        client.cookies.clear()

        response = kakao_login(client)

        assert response.headers["location"] == "/auth/callback"
        assert db_session.query(User).count() == 1
        assert db_session.query(AuthIdentity).count() == 1
        assert db_session.query(RefreshToken).count() == 2

    def test_이미_있는_사용자의_닉네임은_덮어쓰지_않는다(
        self, client: TestClient, db_session: Session, kakao: FakeKakaoClient
    ) -> None:
        kakao_login(client)
        db_session.get(User, 1).nickname = "내가정한닉네임"
        db_session.commit()
        kakao.profile = KakaoProfile(id="12345", nickname="카카오에서바꾼닉네임")

        kakao_login(client)

        db_session.expire_all()
        assert db_session.get(User, 1).nickname == "내가정한닉네임"

    def test_카카오_회원번호가_다르면_다른_계정이다(
        self, client: TestClient, db_session: Session, kakao: FakeKakaoClient
    ) -> None:
        kakao_login(client)
        kakao.profile = KakaoProfile(id="99999", nickname="다른사람")

        kakao_login(client)

        assert db_session.query(User).count() == 2
        assert sorted(i.provider_user_id for i in db_session.query(AuthIdentity)) == ["12345", "99999"]

    @pytest.mark.parametrize(
        ("nickname", "expected"),
        [
            (None, "카카오 사용자"),
            ("", "카카오 사용자"),
            ("   ", "카카오 사용자"),
            ("  공백있는닉  ", "공백있는닉"),
            ("가" * 30, "가" * 20),
        ],
    )
    def test_닉네임이_없거나_길면_기본값으로_다듬는다(
        self,
        client: TestClient,
        db_session: Session,
        kakao: FakeKakaoClient,
        nickname: str | None,
        expected: str,
    ) -> None:
        kakao.profile = KakaoProfile(id="12345", nickname=nickname)

        kakao_login(client)

        assert db_session.query(User).one().nickname == expected

    def test_로컬_계정과_섞이지_않는다(
        self, client: TestClient, db_session: Session
    ) -> None:
        from tests.helpers import signup_payload

        client.post("/api/auth/signup", json=signup_payload())
        client.cookies.clear()

        kakao_login(client)

        providers = sorted(i.provider for i in db_session.query(AuthIdentity))
        assert providers == ["kakao", "local"]
        assert db_session.query(User).count() == 2

    def test_프론트_주소를_따로_설정하면_그_주소로_보낸다(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(
            api.kakao_auth,
            "settings",
            replace(api.kakao_auth.settings, frontend_url="https://momfit.example.com"),
        )

        response = kakao_login(client)

        assert response.headers["location"] == "https://momfit.example.com/auth/callback"


class TestKakaoCallbackFailure:
    def _assert_failed(self, response, error: str, db_session: Session) -> None:
        assert response.status_code == 302
        assert response.headers["location"] == f"/login?error={error}"
        assert db_session.query(User).count() == 0
        assert "refresh_token=" not in "".join(response.headers.get_list("set-cookie"))

    def test_state_쿠키가_없으면_state_mismatch(
        self, client: TestClient, db_session: Session, kakao: FakeKakaoClient
    ) -> None:
        response = client.get(CALLBACK, params={"code": "c", "state": "abc"}, follow_redirects=False)

        self._assert_failed(response, "state_mismatch", db_session)
        assert kakao.exchanged_codes == []

    def test_state_파라미터가_없으면_state_mismatch(
        self, client: TestClient, db_session: Session, kakao: FakeKakaoClient
    ) -> None:
        client.get(LOGIN, follow_redirects=False)

        response = client.get(CALLBACK, params={"code": "c"}, follow_redirects=False)

        self._assert_failed(response, "state_mismatch", db_session)
        assert kakao.exchanged_codes == []

    def test_state가_다르면_state_mismatch이고_카카오를_호출하지_않는다(
        self, client: TestClient, db_session: Session, kakao: FakeKakaoClient
    ) -> None:
        response = kakao_login(client, kakao_state="forged-state")

        self._assert_failed(response, "state_mismatch", db_session)
        assert kakao.exchanged_codes == []

    def test_state_쿠키는_한_번만_쓸_수_있다(
        self, client: TestClient, db_session: Session
    ) -> None:
        login = client.get(LOGIN, follow_redirects=False)
        state = _state_of(login.headers["location"])
        client.get(CALLBACK, params={"code": "c", "state": state}, follow_redirects=False)
        client.cookies.clear()

        # 같은 state를 다시 쓰려 해도 쿠키가 지워져 있어 통과하지 못한다.
        replay = client.get(CALLBACK, params={"code": "c", "state": state}, follow_redirects=False)

        assert replay.headers["location"] == "/login?error=state_mismatch"

    def test_사용자가_취소하면_access_denied(
        self, client: TestClient, db_session: Session
    ) -> None:
        state = _state_of(client.get(LOGIN, follow_redirects=False).headers["location"])

        response = client.get(
            CALLBACK,
            params={"error": "access_denied", "error_description": "user cancel", "state": state},
            follow_redirects=False,
        )

        self._assert_failed(response, "access_denied", db_session)

    def test_취소_응답이어도_state가_틀리면_state_mismatch가_우선한다(
        self, client: TestClient, db_session: Session
    ) -> None:
        client.get(LOGIN, follow_redirects=False)

        response = client.get(
            CALLBACK, params={"error": "access_denied", "state": "forged"}, follow_redirects=False
        )

        self._assert_failed(response, "state_mismatch", db_session)

    def test_그_밖의_카카오_오류는_provider_error(
        self, client: TestClient, db_session: Session
    ) -> None:
        state = _state_of(client.get(LOGIN, follow_redirects=False).headers["location"])

        response = client.get(
            CALLBACK, params={"error": "server_error", "state": state}, follow_redirects=False
        )

        self._assert_failed(response, "provider_error", db_session)

    def test_코드가_없으면_provider_error(
        self, client: TestClient, db_session: Session
    ) -> None:
        state = _state_of(client.get(LOGIN, follow_redirects=False).headers["location"])

        response = client.get(CALLBACK, params={"state": state}, follow_redirects=False)

        self._assert_failed(response, "provider_error", db_session)

    def test_토큰_교환이_실패하면_provider_error(
        self, client: TestClient, db_session: Session, kakao: FakeKakaoClient
    ) -> None:
        kakao.fail_exchange = KakaoError("HTTP 400")

        response = kakao_login(client)

        self._assert_failed(response, "provider_error", db_session)

    def test_프로필_조회가_실패하면_provider_error(
        self, client: TestClient, db_session: Session, kakao: FakeKakaoClient
    ) -> None:
        kakao.fail_profile = KakaoError("HTTP 401")

        response = kakao_login(client)

        self._assert_failed(response, "provider_error", db_session)

    def test_실패해도_state_쿠키는_지운다(self, client: TestClient, kakao: FakeKakaoClient) -> None:
        kakao.fail_exchange = KakaoError("x")

        response = kakao_login(client)

        assert any(
            c.startswith("kakao_state=") and "Max-Age=0" in c
            for c in response.headers.get_list("set-cookie")
        )


class TestKakaoFailureLogging:
    def test_카카오_API_실패_원인을_로그에_남기되_비밀_값은_남기지_않는다(
        self, client: TestClient, kakao: FakeKakaoClient, caplog: pytest.LogCaptureFixture
    ) -> None:
        kakao.fail_exchange = KakaoError("카카오 API 오류 (HTTP 401)")

        with caplog.at_level("WARNING"):
            kakao_login(client, code="secret-auth-code")

        assert "HTTP 401" in caplog.text
        assert "secret-auth-code" not in caplog.text

    def test_시작_단계의_설정_오류도_원인을_남긴다(
        self, client: TestClient, kakao: FakeKakaoClient, caplog: pytest.LogCaptureFixture
    ) -> None:
        kakao.fail_authorize = KakaoNotConfigured("카카오 환경변수가 설정되지 않았습니다.")

        with caplog.at_level("ERROR"):
            client.get(LOGIN, follow_redirects=False)

        assert "카카오 환경변수가 설정되지 않았습니다." in caplog.text
