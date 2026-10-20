import logging
from dataclasses import replace
from typing import Any

import pytest

import services.auth.mailer as mailer_module
from services.auth.mailer import ConsoleMailer, Mail, SmtpMailer, get_mailer, send_safely

MAIL = Mail(to="mom@example.com", subject="제목", body="인증 코드: 123456")


class _FakeSmtp:
    """smtplib.SMTP / SMTP_SSL 대역. 호출 기록만 남긴다."""

    instances: list["_FakeSmtp"] = []

    def __init__(self, host: str, port: int, **kwargs: Any) -> None:
        self.host, self.port, self.kwargs = host, port, kwargs
        self.calls: list[str] = []
        self.sent: list[Any] = []
        _FakeSmtp.instances.append(self)

    def __enter__(self) -> "_FakeSmtp":
        return self

    def __exit__(self, *_: object) -> None:
        return None

    def starttls(self, **_: Any) -> None:
        self.calls.append("starttls")

    def login(self, username: str, password: str) -> None:
        self.calls.append(f"login:{username}:{password}")

    def send_message(self, message: Any) -> None:
        self.calls.append("send")
        self.sent.append(message)


@pytest.fixture(autouse=True)
def _fake_smtp(monkeypatch: pytest.MonkeyPatch) -> None:
    _FakeSmtp.instances = []
    monkeypatch.setattr(mailer_module.smtplib, "SMTP", _FakeSmtp)
    monkeypatch.setattr(mailer_module.smtplib, "SMTP_SSL", _FakeSmtp)


def test_587_포트는_STARTTLS_후_로그인하고_발송한다() -> None:
    SmtpMailer("smtp.example.com", 587, "user", "pw", "noreply@example.com").send(MAIL)

    smtp = _FakeSmtp.instances[0]
    assert (smtp.host, smtp.port) == ("smtp.example.com", 587)
    assert smtp.calls == ["starttls", "login:user:pw", "send"]
    message = smtp.sent[0]
    assert message["From"] == "noreply@example.com"
    assert message["To"] == "mom@example.com"
    assert message["Subject"] == "제목"
    assert "123456" in message.get_content()


def test_465_포트는_SSL로_접속하고_STARTTLS는_쓰지_않는다() -> None:
    SmtpMailer("smtp.example.com", 465, "user", "pw", "noreply@example.com").send(MAIL)

    smtp = _FakeSmtp.instances[0]
    assert "starttls" not in smtp.calls
    assert smtp.calls == ["login:user:pw", "send"]


def test_계정이_없으면_로그인을_건너뛴다() -> None:
    SmtpMailer("localhost", 587, "", "", "noreply@example.com").send(MAIL)

    assert _FakeSmtp.instances[0].calls == ["starttls", "send"]


def test_콘솔_메일러는_로그만_남긴다(caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.INFO, logger="uvicorn.error"):
        ConsoleMailer().send(MAIL)

    assert "123456" in caplog.text
    assert _FakeSmtp.instances == []


class TestGetMailer:
    @pytest.fixture(autouse=True)
    def _clear_cache(self):
        get_mailer.cache_clear()
        yield
        get_mailer.cache_clear()

    def _use(self, monkeypatch: pytest.MonkeyPatch, **overrides: Any) -> None:
        monkeypatch.setattr(
            mailer_module, "settings", replace(mailer_module.settings, **overrides)
        )

    def test_console(self, monkeypatch: pytest.MonkeyPatch) -> None:
        self._use(monkeypatch, mail_backend="console")

        assert isinstance(get_mailer(), ConsoleMailer)

    def test_smtp(self, monkeypatch: pytest.MonkeyPatch) -> None:
        self._use(monkeypatch, mail_backend="smtp", smtp_host="h", mail_from="a@b.com")

        assert isinstance(get_mailer(), SmtpMailer)

    def test_smtp_설정이_없으면_예외(self, monkeypatch: pytest.MonkeyPatch) -> None:
        self._use(monkeypatch, mail_backend="smtp", smtp_host="", mail_from="")

        with pytest.raises(RuntimeError):
            get_mailer()

    def test_알_수_없는_백엔드는_예외(self, monkeypatch: pytest.MonkeyPatch) -> None:
        self._use(monkeypatch, mail_backend="carrier-pigeon")

        with pytest.raises(RuntimeError):
            get_mailer()


def test_발송_실패는_삼키고_수신자나_본문을_로그에_남기지_않는다(
    caplog: pytest.LogCaptureFixture,
) -> None:
    class Broken:
        def send(self, mail: Mail) -> None:
            raise ConnectionError("smtp down")

    with caplog.at_level(logging.ERROR):
        send_safely(Broken(), MAIL)

    assert "이메일 발송에 실패했습니다." in caplog.text
    assert "mom@example.com" not in caplog.text.replace("smtp down", "")
    assert "123456" not in caplog.text
