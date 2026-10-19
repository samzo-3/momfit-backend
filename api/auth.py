"""인증 라우터."""

from fastapi import APIRouter, Cookie, Depends, Query, Response
from sqlalchemy.orm import Session

from core.config import settings
from db.session import get_db
from schemas.auth import (
    CheckLoginIdResponse,
    LoginRequest,
    SignupRequest,
    TokenResponse,
)
from services import auth_service
from services.auth_service import IssuedTokens

router = APIRouter(prefix="/api/auth", tags=["auth"])

REFRESH_COOKIE_NAME = "refresh_token"
# refresh 쿠키는 인증 경로에서만 전송되도록 제한한다.
REFRESH_COOKIE_PATH = "/api/auth"


def _set_refresh_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        REFRESH_COOKIE_NAME,
        token,
        max_age=settings.refresh_token_expire_days * 24 * 60 * 60,
        path=REFRESH_COOKIE_PATH,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
    )


def _token_response(response: Response, tokens: IssuedTokens) -> TokenResponse:
    _set_refresh_cookie(response, tokens.refresh_token)
    return TokenResponse(access_token=tokens.access_token, expires_in=tokens.expires_in)


@router.get("/check-login-id", response_model=CheckLoginIdResponse)
def check_login_id(
    login_id: str = Query(min_length=1, max_length=50), db: Session = Depends(get_db)
) -> CheckLoginIdResponse:
    """아이디 중복 여부를 확인한다."""
    return CheckLoginIdResponse(available=auth_service.is_login_id_available(db, login_id))


@router.post("/signup", response_model=TokenResponse, status_code=201)
def signup(
    request: SignupRequest, response: Response, db: Session = Depends(get_db)
) -> TokenResponse:
    """로컬 계정을 만들고 로그인 처리한다."""
    return _token_response(response, auth_service.signup(db, request))


@router.post("/login", response_model=TokenResponse)
def login(
    request: LoginRequest, response: Response, db: Session = Depends(get_db)
) -> TokenResponse:
    """아이디와 비밀번호로 로그인한다."""
    return _token_response(response, auth_service.login(db, request))


@router.post("/refresh", response_model=TokenResponse)
def refresh(
    response: Response,
    refresh_token: str | None = Cookie(default=None),
    db: Session = Depends(get_db),
) -> TokenResponse:
    """refresh 쿠키로 access 토큰을 재발급하고 refresh 토큰을 교체한다."""
    return _token_response(response, auth_service.refresh(db, refresh_token))


@router.post("/logout", status_code=204)
def logout(
    response: Response,
    refresh_token: str | None = Cookie(default=None),
    db: Session = Depends(get_db),
) -> None:
    """refresh 토큰을 폐기하고 쿠키를 삭제한다."""
    auth_service.logout(db, refresh_token)
    response.delete_cookie(REFRESH_COOKIE_NAME, path=REFRESH_COOKIE_PATH)
