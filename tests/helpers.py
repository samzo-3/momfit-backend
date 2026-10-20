"""API 테스트 공통 헬퍼."""

from datetime import timedelta
from typing import Any

from core.clock import today_kst
from core.security import create_email_verification_token


def signup_payload(**overrides: Any) -> dict[str, Any]:
    """유효한 가입 요청 본문을 만든다. 이메일 인증 토큰도 함께 발급한다."""
    email = overrides.get("email", "mom@example.com")
    payload: dict[str, Any] = {
        "login_id": "momfit01",
        "password": "password1",
        "nickname": "맘핏",
        "email": email,
        "email_verification_token": create_email_verification_token(email, "signup"),
        "due_date": (today_kst() + timedelta(days=84)).isoformat(),
        "exercise_level": "low",
        "consents": {"terms": True, "health_data": True},
    }
    payload.update(overrides)
    return payload


def kakao_login(client, kakao_state: str | None = None, code: str = "auth-code"):
    """카카오 로그인 전체 흐름(인가 요청 → 콜백)을 수행하고 콜백 응답을 반환한다.

    kakao_state를 주면 콜백에 그 값을 state로 보내 state 불일치를 흉내 낸다.
    """
    login = client.get("/api/auth/kakao/login", follow_redirects=False)
    state = login.headers["location"].split("state=")[1].split("&")[0]
    return client.get(
        "/api/auth/kakao/callback",
        params={"code": code, "state": kakao_state or state},
        follow_redirects=False,
    )
