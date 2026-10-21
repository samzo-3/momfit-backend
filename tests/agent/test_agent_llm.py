"""LLM 제공자 검사. 실제 API는 부르지 않는다.

Gemini는 내 컴퓨터에 띄운 가짜 서버로 실제 SDK를 그대로 돌려 본다. SDK 안쪽의 재시도·대기는
설정만 봐서는 알 수 없어서(설정값이 Client를 만들며 바뀐 적이 있다), 서버가 받은 요청 수와
걸린 시간으로 확인한다.
"""

import json
import threading
import time
from collections.abc import Generator
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from services.agent.llm import GeminiLlm, LlmError, LlmRateLimitedError, LlmTimeoutError

# 가짜 서버가 늦게 답할 때 기다리는 시간. 클라이언트 제한 시간(아래 0.5초)보다 충분히 길다.
SLOW_SECONDS = 3.0


class FakeGeminiServer(ThreadingHTTPServer):
    """generateContent 요청을 세고, mode에 따라 정상·503·429·늦은 답을 돌려준다."""

    daemon_threads = True

    def __init__(self) -> None:
        super().__init__(("127.0.0.1", 0), FakeGeminiHandler)
        self.mode = "ok"
        self.requests: list[dict] = []


class FakeGeminiHandler(BaseHTTPRequestHandler):
    server: FakeGeminiServer

    def log_message(self, *args) -> None:
        return None

    def _reply(self, status: int, body: dict, headers: dict | None = None) -> None:
        data = json.dumps(body).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        for name, value in (headers or {}).items():
            self.send_header(name, value)
        self.end_headers()
        self.wfile.write(data)

    def do_POST(self) -> None:
        length = int(self.headers.get("Content-Length", 0))
        self.server.requests.append(
            {"path": self.path, "body": json.loads(self.rfile.read(length) or b"{}")}
        )
        mode = self.server.mode
        try:
            if mode == "503":
                # 재시도한다면 30초를 기다리게 하는 Retry-After를 일부러 붙인다.
                self._reply(
                    503,
                    {"error": {"code": 503, "message": "high demand", "status": "UNAVAILABLE"}},
                    {"Retry-After": "30"},
                )
            elif mode == "429":
                self._reply(
                    429,
                    {"error": {"code": 429, "message": "quota", "status": "RESOURCE_EXHAUSTED"}},
                    {"Retry-After": "30"},
                )
            else:
                if mode == "slow":
                    time.sleep(SLOW_SECONDS)
                self._reply(
                    200,
                    {
                        "candidates": [
                            {"content": {"role": "model", "parts": [{"text": '{"ok": true}'}]}}
                        ],
                        "usageMetadata": {"promptTokenCount": 11, "candidatesTokenCount": 22},
                    },
                )
        except (BrokenPipeError, ConnectionResetError):
            # 늦은 답을 보낼 때 클라이언트가 이미 포기하고 연결을 끊었으면 그냥 끝낸다.
            return


@pytest.fixture()
def fake_gemini(monkeypatch: pytest.MonkeyPatch) -> Generator[FakeGeminiServer, None, None]:
    server = FakeGeminiServer()
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    monkeypatch.setenv("GOOGLE_GEMINI_BASE_URL", f"http://127.0.0.1:{server.server_port}")
    yield server
    server.shutdown()
    server.server_close()


def _llm() -> GeminiLlm:
    return GeminiLlm(model="gemini-test", api_key="test-key")


def test_Gemini는_시스템_프롬프트와_입력을_보내고_답과_토큰_수를_돌려준다(
    fake_gemini: FakeGeminiServer,
) -> None:
    text, usage = _llm().generate("시스템 규칙", '{"steps": []}', timeout=5.0)

    assert text == '{"ok": true}'
    assert (usage.input_tokens, usage.output_tokens) == (11, 22)
    [request] = fake_gemini.requests
    assert "gemini-test:generateContent" in request["path"]
    assert request["body"]["systemInstruction"]["parts"][0]["text"] == "시스템 규칙"
    assert request["body"]["contents"][0]["parts"][0]["text"] == '{"steps": []}'


def test_Gemini는_503을_받으면_재시도하지_않고_바로_실패한다(
    fake_gemini: FakeGeminiServer,
) -> None:
    fake_gemini.mode = "503"
    started = time.monotonic()

    with pytest.raises(LlmError):
        _llm().generate("system", "user", timeout=5.0)

    # 재시도했다면 요청이 2번 이상이고, Retry-After(30초)만큼 잠들었을 것이다.
    assert len(fake_gemini.requests) == 1
    assert time.monotonic() - started < 2.0


def test_Gemini는_429를_받으면_재시도하지_않고_한도_초과로_알린다(
    fake_gemini: FakeGeminiServer,
) -> None:
    fake_gemini.mode = "429"

    with pytest.raises(LlmRateLimitedError):
        _llm().generate("system", "user", timeout=5.0)

    assert len(fake_gemini.requests) == 1


def test_Gemini는_제한_시간이_지나면_한_번만_기다리고_포기한다(
    fake_gemini: FakeGeminiServer,
) -> None:
    fake_gemini.mode = "slow"
    started = time.monotonic()

    with pytest.raises(LlmTimeoutError):
        _llm().generate("system", "user", timeout=0.5)

    assert len(fake_gemini.requests) == 1
    assert time.monotonic() - started < SLOW_SECONDS
