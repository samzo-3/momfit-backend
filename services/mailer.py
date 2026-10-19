"""메일 발송 인터페이스와 구현체. 발송 수단은 환경변수(MAIL_BACKEND)로 고른다."""

import logging
import smtplib
import ssl
from dataclasses import dataclass
from email.message import EmailMessage
from functools import lru_cache
from typing import Protocol

from core.config import settings

logger = logging.getLogger(__name__)
# uvicorn은 앱 로거를 기본 설정하지 않으므로, 개발용 콘솔 출력은 uvicorn 로거로 보낸다.
_console_logger = logging.getLogger("uvicorn.error")


@dataclass(frozen=True)
class Mail:
    """보낼 메일 한 통."""

    to: str
    subject: str
    body: str


class Mailer(Protocol):
    """메일 발송 인터페이스. 발송 수단을 바꿔도 서비스 코드는 그대로 둔다."""

    def send(self, mail: Mail) -> None: ...


class ConsoleMailer:
    """개발용. 메일을 보내지 않고 서버 로그에만 출력한다. 운영에서 쓰지 않는다."""

    def send(self, mail: Mail) -> None:
        _console_logger.info("[개발용 메일] to=%s subject=%s\n%s", mail.to, mail.subject, mail.body)


class SmtpMailer:
    """SMTP 서버로 발송한다. 465 포트는 SSL, 그 외에는 STARTTLS를 쓴다."""

    def __init__(
        self, host: str, port: int, username: str, password: str, sender: str
    ) -> None:
        self._host = host
        self._port = port
        self._username = username
        self._password = password
        self._sender = sender

    def send(self, mail: Mail) -> None:
        message = EmailMessage()
        message["From"] = self._sender
        message["To"] = mail.to
        message["Subject"] = mail.subject
        message.set_content(mail.body)

        context = ssl.create_default_context()
        if self._port == 465:
            with smtplib.SMTP_SSL(self._host, self._port, context=context, timeout=10) as smtp:
                self._login_and_send(smtp, message)
        else:
            with smtplib.SMTP(self._host, self._port, timeout=10) as smtp:
                smtp.starttls(context=context)
                self._login_and_send(smtp, message)

    def _login_and_send(self, smtp: smtplib.SMTP, message: EmailMessage) -> None:
        if self._username:
            smtp.login(self._username, self._password)
        smtp.send_message(message)


@lru_cache
def get_mailer() -> Mailer:
    """설정에 맞는 메일러를 반환한다. FastAPI 의존성으로 쓰며, 테스트에서는 교체한다."""
    if settings.mail_backend == "console":
        return ConsoleMailer()
    if settings.mail_backend == "smtp":
        if not (settings.smtp_host and settings.mail_from):
            raise RuntimeError("SMTP_HOST와 MAIL_FROM 환경변수가 설정되지 않았습니다.")
        return SmtpMailer(
            settings.smtp_host,
            settings.smtp_port,
            settings.smtp_username,
            settings.smtp_password,
            settings.mail_from,
        )
    raise RuntimeError(f"지원하지 않는 MAIL_BACKEND입니다: {settings.mail_backend}")


def send_safely(mailer: Mailer, mail: Mail) -> None:
    """백그라운드에서 발송한다. 실패해도 요청 결과는 바꾸지 않고, 수신자·내용 없이 로그만 남긴다."""
    try:
        mailer.send(mail)
    except Exception:
        logger.exception("이메일 발송에 실패했습니다.")
