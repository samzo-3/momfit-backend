"""카카오 로그인 라우터. 브라우저가 직접 이동하는 경로라 JSON이 아니라 리다이렉트로 응답한다."""

import logging
import secrets

from fastapi import APIRouter, Cookie, Depends, Query
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from api.auth import set_refresh_cookie
from core.config import settings
from db.session import get_db
from services import kakao_auth_service
from services.kakao_client import KakaoClient, KakaoError, get_kakao_client

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/auth/kakao", tags=["auth"])

STATE_COOKIE_NAME = "kakao_state"
STATE_COOKIE_PATH = "/api/auth/kakao"
STATE_COOKIE_MAX_AGE = 10 * 60


def _redirect(path: str) -> RedirectResponse:
    # 프록시를 거치는 같은 도메인이면 상대 경로, 따로 설정했다면 그 주소로 보낸다.
    return RedirectResponse(f"{settings.frontend_url}{path}", status_code=302)


def _failure(code: str) -> RedirectResponse:
    """실패하면 프론트 로그인 화면으로 보내고 오류 코드만 전달한다."""
    response = _redirect(f"/login?error={code}")
    response.delete_cookie(STATE_COOKIE_NAME, path=STATE_COOKIE_PATH)
    return response


@router.get("/login")
def kakao_login(client: KakaoClient = Depends(get_kakao_client)) -> RedirectResponse:
    """카카오 인가 페이지로 보낸다. CSRF 방지용 state를 쿠키에도 저장한다."""
    state = secrets.token_urlsafe(32)
    try:
        url = client.authorize_url(state)
    except KakaoError:
        logger.error("카카오 로그인이 설정되지 않았습니다.")
        return _failure("provider_error")

    response = RedirectResponse(url, status_code=302)
    response.set_cookie(
        STATE_COOKIE_NAME,
        state,
        max_age=STATE_COOKIE_MAX_AGE,
        path=STATE_COOKIE_PATH,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
    )
    return response


@router.get("/callback")
def kakao_callback(
    code: str | None = Query(default=None),
    state: str | None = Query(default=None),
    error: str | None = Query(default=None),
    kakao_state: str | None = Cookie(default=None),
    db: Session = Depends(get_db),
    client: KakaoClient = Depends(get_kakao_client),
) -> RedirectResponse:
    """인가 코드를 교환해 로그인시키고 프론트의 /auth/callback으로 보낸다."""
    # 취소 응답에도 state가 오므로, 무엇보다 먼저 state를 검증한다.
    if not state or not kakao_state or not secrets.compare_digest(state, kakao_state):
        return _failure("state_mismatch")
    if error:
        return _failure("access_denied" if error == "access_denied" else "provider_error")
    if not code:
        return _failure("provider_error")

    try:
        profile = client.fetch_profile(client.exchange_code(code))
    except KakaoError:
        logger.warning("카카오 로그인 중 카카오 API 호출에 실패했습니다.")
        return _failure("provider_error")

    tokens = kakao_auth_service.login_with_kakao(db, profile)
    response = _redirect("/auth/callback")
    set_refresh_cookie(response, tokens.refresh_token)
    response.delete_cookie(STATE_COOKIE_NAME, path=STATE_COOKIE_PATH)
    return response
