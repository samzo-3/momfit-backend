import pytest

from core.config import get_settings


def test_인증_설정_기본값(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in (
        "JWT_SECRET",
        "JWT_ALGORITHM",
        "ACCESS_TOKEN_EXPIRE_MINUTES",
        "REFRESH_TOKEN_EXPIRE_DAYS",
        "COOKIE_SECURE",
    ):
        monkeypatch.delenv(name, raising=False)

    settings = get_settings()

    assert settings.jwt_algorithm == "HS256"
    assert settings.access_token_expire_minutes == 15
    assert settings.refresh_token_expire_days == 14
    assert settings.cookie_secure is True


def test_환경변수로_인증_설정을_덮어쓴다(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("JWT_SECRET", "secret")
    monkeypatch.setenv("ACCESS_TOKEN_EXPIRE_MINUTES", "30")
    monkeypatch.setenv("COOKIE_SECURE", "false")

    settings = get_settings()

    assert settings.require_jwt_secret() == "secret"
    assert settings.access_token_expire_minutes == 30
    assert settings.cookie_secure is False


def test_JWT_SECRET이_없으면_토큰_발급용_조회가_실패한다(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("JWT_SECRET", raising=False)

    with pytest.raises(RuntimeError):
        get_settings().require_jwt_secret()


def test_탈퇴_유예_설정_기본값은_30일과_6시간_주기다(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ACCOUNT_GRACE_DAYS", raising=False)
    monkeypatch.delenv("ACCOUNT_PURGE_INTERVAL_HOURS", raising=False)

    settings = get_settings()

    assert settings.account_grace_days == 30
    assert settings.account_purge_interval_hours == 6


def test_환경변수로_탈퇴_유예_설정을_바꾼다(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ACCOUNT_GRACE_DAYS", "7")
    monkeypatch.setenv("ACCOUNT_PURGE_INTERVAL_HOURS", "0")

    settings = get_settings()

    assert settings.account_grace_days == 7
    assert settings.account_purge_interval_hours == 0


def test_챗봇_주소_기본값과_덮어쓰기(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("CHATBOT_URL", raising=False)
    monkeypatch.delenv("CHATBOT_TIMEOUT_SECONDS", raising=False)

    default = get_settings()

    assert default.chatbot_url == "http://momfit-chatbot.team.svc.cluster.local:8000"
    assert default.chatbot_timeout_seconds == 60.0

    monkeypatch.setenv("CHATBOT_URL", "http://localhost:8100/")
    monkeypatch.setenv("CHATBOT_TIMEOUT_SECONDS", "30")

    overridden = get_settings()

    assert overridden.chatbot_url == "http://localhost:8100"
    assert overridden.chatbot_timeout_seconds == 30.0
