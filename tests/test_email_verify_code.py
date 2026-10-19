from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from core.clock import utc_now
from core.security import verify_email_verification_token
from models.email_verification import EmailVerification
from services import email_verification_service as service
from tests.conftest import FakeMailer
from tests.helpers import signup_payload

SEND = "/api/auth/email/send-code"
VERIFY = "/api/auth/email/verify-code"


def _send_code(client: TestClient, mailer: FakeMailer, email="mom@example.com", purpose="signup") -> str:
    assert client.post(SEND, json={"email": email, "purpose": purpose}).status_code == 204
    return mailer.last_code()


def _verify(client: TestClient, code: str, email="mom@example.com", purpose="signup"):
    return client.post(VERIFY, json={"email": email, "code": code, "purpose": purpose})


def _wrong(code: str) -> str:
    return "000000" if code != "000000" else "111111"


def test_올바른_코드를_입력하면_토큰을_발급한다(client: TestClient, mailer: FakeMailer) -> None:
    code = _send_code(client, mailer)

    response = _verify(client, code)

    assert response.status_code == 200
    body = response.json()
    assert body["expires_in"] == 1800
    verify_email_verification_token(body["email_verification_token"], "mom@example.com", "signup")


def test_인증_후_받은_토큰으로_가입할_수_있다(client: TestClient, mailer: FakeMailer) -> None:
    token = _verify(client, _send_code(client, mailer)).json()["email_verification_token"]

    response = client.post(
        "/api/auth/signup", json=signup_payload(email_verification_token=token)
    )

    assert response.status_code == 201


def test_한_번_쓴_코드는_다시_쓸_수_없다(client: TestClient, mailer: FakeMailer) -> None:
    code = _send_code(client, mailer)
    _verify(client, code)

    response = _verify(client, code)

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "CODE_INVALID"


def test_틀린_코드는_CODE_INVALID(client: TestClient, mailer: FakeMailer) -> None:
    code = _send_code(client, mailer)

    response = _verify(client, _wrong(code))

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "CODE_INVALID"


def test_발송한_적_없는_이메일도_CODE_INVALID(client: TestClient) -> None:
    response = _verify(client, "123456", email="nobody@example.com")

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "CODE_INVALID"


def test_5회_틀리면_올바른_코드도_무효화된다(
    client: TestClient, mailer: FakeMailer, db_session: Session
) -> None:
    code = _send_code(client, mailer)

    for _ in range(5):
        assert _verify(client, _wrong(code)).status_code == 400
    response = _verify(client, code)

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "CODE_INVALID"
    assert db_session.query(EmailVerification).one().consumed_at is not None


def test_4회_틀린_뒤에는_올바른_코드가_통과한다(client: TestClient, mailer: FakeMailer) -> None:
    code = _send_code(client, mailer)
    for _ in range(4):
        _verify(client, _wrong(code))

    assert _verify(client, code).status_code == 200


def test_만료된_코드는_CODE_EXPIRED(
    client: TestClient, mailer: FakeMailer, db_session: Session
) -> None:
    code = _send_code(client, mailer)
    db_session.query(EmailVerification).one().expires_at = utc_now() - timedelta(seconds=1)
    db_session.commit()

    response = _verify(client, code)

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "CODE_EXPIRED"


def test_재발송하면_이전_코드는_쓸_수_없다(
    client: TestClient,
    mailer: FakeMailer,
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    codes = iter([111111, 222222])
    monkeypatch.setattr(service.secrets, "randbelow", lambda _: next(codes))
    first = _send_code(client, mailer)
    # 재발송 간격 제한을 우회하기 위해 첫 기록의 시각을 과거로 돌린다.
    db_session.query(EmailVerification).one().created_at = utc_now() - timedelta(minutes=5)
    db_session.commit()
    second = _send_code(client, mailer)

    assert (first, second) == ("111111", "222222")
    assert _verify(client, first).status_code == 400
    assert _verify(client, second).status_code == 200


def test_용도가_다르면_인증되지_않는다(client: TestClient, mailer: FakeMailer) -> None:
    code = _send_code(client, mailer, purpose="signup")

    response = _verify(client, code, purpose="password_reset")

    assert response.status_code == 400


def test_코드_형식이_틀리면_422(client: TestClient) -> None:
    for code in ("12345", "1234567", "abcdef", ""):
        assert _verify(client, code).status_code == 422, code
