import io
import json
import urllib.error
import urllib.parse
from typing import Any

import pytest

import services.auth.kakao_client as module
from services.auth.kakao_client import (
    KakaoClient,
    KakaoError,
    KakaoNotConfigured,
    KakaoProfile,
    get_kakao_client,
)


class _Response:
    def __init__(self, body: Any) -> None:
        self._raw = body if isinstance(body, bytes) else json.dumps(body).encode()

    def __enter__(self) -> "_Response":
        return self

    def __exit__(self, *_: object) -> None:
        return None

    def read(self) -> bytes:
        return self._raw


@pytest.fixture()
def calls(monkeypatch: pytest.MonkeyPatch) -> list[Any]:
    """urlopen 호출을 가로채 기록한다. 응답은 calls.reply로 정한다."""
    class Calls(list):
        reply: Any = {}

    calls = Calls()

    def fake_urlopen(request, timeout=None):
        calls.append((request, timeout))
        if isinstance(calls.reply, Exception):
            raise calls.reply
        return _Response(calls.reply)

    monkeypatch.setattr(module.urllib.request, "urlopen", fake_urlopen)
    return calls


def _client(**overrides: str) -> KakaoClient:
    values = {
        "client_id": "rest-key",
        "client_secret": "secret-value",
        "redirect_uri": "http://localhost:5174/api/auth/kakao/callback",
        "admin_key": "admin-key",
    }
    values.update(overrides)
    return KakaoClient(**values)


def _form(request) -> dict[str, str]:
    return dict(urllib.parse.parse_qsl(request.data.decode()))


def test_인가_주소에_필요한_파라미터가_들어간다() -> None:
    url = _client().authorize_url("state-123")

    parsed = urllib.parse.urlparse(url)
    query = dict(urllib.parse.parse_qsl(parsed.query))
    assert f"{parsed.scheme}://{parsed.netloc}{parsed.path}" == "https://kauth.kakao.com/oauth/authorize"
    assert query == {
        "client_id": "rest-key",
        "redirect_uri": "http://localhost:5174/api/auth/kakao/callback",
        "response_type": "code",
        "scope": "profile_nickname",
        "state": "state-123",
    }


def test_설정이_없으면_인가_주소를_만들_수_없다() -> None:
    with pytest.raises(KakaoNotConfigured):
        _client(client_id="").authorize_url("s")
    with pytest.raises(KakaoNotConfigured):
        _client(redirect_uri="").authorize_url("s")


def test_코드를_토큰으로_교환한다(calls: list) -> None:
    calls.reply = {"access_token": "kakao-token", "token_type": "bearer"}

    token = _client().exchange_code("the-code")

    request, timeout = calls[0]
    assert token == "kakao-token"
    assert request.full_url == "https://kauth.kakao.com/oauth/token"
    assert request.get_method() == "POST"
    assert request.get_header("Content-type") == "application/x-www-form-urlencoded;charset=utf-8"
    assert _form(request) == {
        "grant_type": "authorization_code",
        "client_id": "rest-key",
        "client_secret": "secret-value",
        "redirect_uri": "http://localhost:5174/api/auth/kakao/callback",
        "code": "the-code",
    }
    assert timeout == 10


def test_토큰_응답에_access_token이_없으면_실패한다(calls: list) -> None:
    calls.reply = {"token_type": "bearer"}

    with pytest.raises(KakaoError):
        _client().exchange_code("c")


def test_클라이언트_시크릿이_없으면_토큰_교환을_하지_않는다(calls: list) -> None:
    with pytest.raises(KakaoNotConfigured):
        _client(client_secret="").exchange_code("c")

    assert calls == []


def test_프로필에서_회원번호와_닉네임을_읽는다(calls: list) -> None:
    calls.reply = {"id": 987654321, "kakao_account": {"profile": {"nickname": "카카오맘"}}}

    profile = _client().fetch_profile("access-1")

    request, _ = calls[0]
    assert profile == KakaoProfile(id="987654321", nickname="카카오맘")
    assert request.full_url == "https://kapi.kakao.com/v2/user/me"
    assert request.get_method() == "GET"
    assert request.get_header("Authorization") == "Bearer access-1"
    assert request.data is None


@pytest.mark.parametrize(
    "reply",
    [{"id": 1}, {"id": 1, "kakao_account": {}}, {"id": 1, "kakao_account": {"profile": {}}}],
)
def test_닉네임이_없어도_프로필을_읽는다(calls: list, reply: dict) -> None:
    calls.reply = reply

    assert _client().fetch_profile("t").nickname is None


def test_회원번호가_없으면_프로필_조회에_실패한다(calls: list) -> None:
    calls.reply = {"kakao_account": {"profile": {"nickname": "x"}}}

    with pytest.raises(KakaoError):
        _client().fetch_profile("t")


def test_어드민_키로_연결을_끊는다(calls: list) -> None:
    calls.reply = {"id": 12345}

    _client().unlink("12345")

    request, _ = calls[0]
    assert request.full_url == "https://kapi.kakao.com/v1/user/unlink"
    assert request.get_method() == "POST"
    assert request.get_header("Authorization") == "KakaoAK admin-key"
    assert _form(request) == {"target_id_type": "user_id", "target_id": "12345"}


def test_어드민_키가_없으면_연결을_끊지_않는다(calls: list) -> None:
    with pytest.raises(KakaoNotConfigured):
        _client(admin_key="").unlink("1")

    assert calls == []


def test_HTTP_오류는_상태_코드만_담은_KakaoError가_된다(calls: list) -> None:
    calls.reply = urllib.error.HTTPError(
        "https://kauth.kakao.com/oauth/token", 400, "Bad", {}, io.BytesIO(b'{"error":"invalid_grant","code":"the-code"}')
    )

    with pytest.raises(KakaoError) as exc_info:
        _client().exchange_code("the-code")

    message = str(exc_info.value)
    assert "400" in message
    assert "the-code" not in message
    assert "secret-value" not in message


@pytest.mark.parametrize("failure", [urllib.error.URLError("down"), TimeoutError(), OSError("net")])
def test_연결_실패는_KakaoError가_된다(calls: list, failure: Exception) -> None:
    calls.reply = failure

    with pytest.raises(KakaoError):
        _client().fetch_profile("t")


@pytest.mark.parametrize("body", [b"not json", b"[1, 2]"])
def test_JSON이_아니거나_객체가_아니면_KakaoError(calls: list, body: bytes) -> None:
    calls.reply = body

    with pytest.raises(KakaoError):
        _client().fetch_profile("t")


def test_설정에서_클라이언트를_만들고_빈_설정이어도_만들어진다() -> None:
    get_kakao_client.cache_clear()

    client = get_kakao_client()

    assert isinstance(client, KakaoClient)
    with pytest.raises(KakaoNotConfigured):
        client.authorize_url("s")
    get_kakao_client.cache_clear()
