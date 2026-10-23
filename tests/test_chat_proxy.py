"""/api/chat/* 프록시 테스트. 챗봇 서비스는 httpx.MockTransport로 흉내 낸다."""

import json
from collections.abc import Callable, Generator

import httpx
import pytest
from fastapi.testclient import TestClient

from api.chat_proxy import get_chatbot_client
from main import app
from tests.helpers import signup_payload

Handler = Callable[[httpx.Request], httpx.Response]


@pytest.fixture()
def upstream_requests() -> list[httpx.Request]:
    return []


@pytest.fixture()
def chatbot(
    client: TestClient, upstream_requests: list[httpx.Request]
) -> Generator[dict[str, Handler], None, None]:
    """챗봇 응답을 테스트마다 바꿀 수 있게 handler를 담아 두는 상자."""
    box: dict[str, Handler] = {
        "handler": lambda request: httpx.Response(200, json={"kind": "answer"})
    }

    def handle(request: httpx.Request) -> httpx.Response:
        upstream_requests.append(request)
        return box["handler"](request)

    mock_client = httpx.AsyncClient(
        base_url="http://chatbot.test", transport=httpx.MockTransport(handle)
    )
    app.dependency_overrides[get_chatbot_client] = lambda: mock_client
    yield box
    app.dependency_overrides.pop(get_chatbot_client, None)


def _token(client: TestClient) -> str:
    response = client.post("/api/auth/signup", json=signup_payload())
    assert response.status_code == 201
    return response.json()["access_token"]


def _bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_질문을_챗봇에_전달하고_답을_그대로_돌려준다(
    client: TestClient,
    chatbot: dict[str, Handler],
    upstream_requests: list[httpx.Request],
) -> None:
    chatbot["handler"] = lambda request: httpx.Response(
        200, json={"kind": "answer", "answer": "걷기를 권장해요.", "sources": []}
    )
    token = _token(client)

    response = client.post(
        "/api/chat/messages", json={"question": "걷기 괜찮아요?"}, headers=_bearer(token)
    )

    assert response.status_code == 200
    assert response.json() == {"kind": "answer", "answer": "걷기를 권장해요.", "sources": []}
    (sent,) = upstream_requests
    assert sent.method == "POST"
    assert sent.url.path == "/api/chat/messages"
    assert sent.headers["Authorization"] == f"Bearer {token}"
    assert json.loads(sent.content) == {"question": "걷기 괜찮아요?"}


def test_토큰이_없으면_챗봇을_부르지_않고_401이다(
    client: TestClient,
    chatbot: dict[str, Handler],
    upstream_requests: list[httpx.Request],
) -> None:
    response = client.post("/api/chat/messages", json={"question": "q"})

    assert response.status_code == 401
    assert upstream_requests == []


def test_챗봇의_에러_응답을_상태와_함께_전달한다(
    client: TestClient, chatbot: dict[str, Handler]
) -> None:
    error = {"error": {"code": "RATE_LIMITED", "message": "잠시 후 다시 물어봐 주세요."}}
    chatbot["handler"] = lambda request: httpx.Response(
        429, json=error, headers={"Retry-After": "30"}
    )
    token = _token(client)

    response = client.post(
        "/api/chat/messages", json={"question": "q"}, headers=_bearer(token)
    )

    assert response.status_code == 429
    assert response.json() == error
    assert response.headers["Retry-After"] == "30"


def test_검증_실패_422도_그대로_전달한다(
    client: TestClient, chatbot: dict[str, Handler]
) -> None:
    error = {"error": {"code": "VALIDATION_ERROR", "message": "요청 값이 올바르지 않습니다."}}
    chatbot["handler"] = lambda request: httpx.Response(422, json=error)
    token = _token(client)

    response = client.post(
        "/api/chat/messages", json={"question": ""}, headers=_bearer(token)
    )

    assert response.status_code == 422
    assert response.json() == error


@pytest.mark.parametrize(
    "failure",
    [
        httpx.ConnectError("refused"),
        httpx.ReadTimeout("timeout"),
    ],
)
def test_챗봇에_연결하지_못하면_503이다(
    client: TestClient, chatbot: dict[str, Handler], failure: Exception
) -> None:
    def fail(request: httpx.Request) -> httpx.Response:
        raise failure

    chatbot["handler"] = fail
    token = _token(client)

    response = client.post(
        "/api/chat/messages", json={"question": "q"}, headers=_bearer(token)
    )

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "SERVICE_UNAVAILABLE"


@pytest.mark.parametrize("path", ["/api/chat/health", "/api/chat/ready"])
def test_상태_확인은_인증_없이_챗봇_응답을_전달한다(
    client: TestClient,
    chatbot: dict[str, Handler],
    upstream_requests: list[httpx.Request],
    path: str,
) -> None:
    chatbot["handler"] = lambda request: httpx.Response(200, json={"status": "ok"})

    response = client.get(path)

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    assert upstream_requests[0].url.path == path
    assert "Authorization" not in upstream_requests[0].headers


def test_챗봇이_내려가도_상태_확인은_503이다(
    client: TestClient, chatbot: dict[str, Handler]
) -> None:
    def fail(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused")

    chatbot["handler"] = fail

    response = client.get("/api/chat/ready")

    assert response.status_code == 503


def test_허용하지_않은_챗봇_경로는_전달하지_않는다(
    client: TestClient,
    chatbot: dict[str, Handler],
    upstream_requests: list[httpx.Request],
) -> None:
    response = client.get("/api/chat/docs")

    assert response.status_code == 404
    assert upstream_requests == []
