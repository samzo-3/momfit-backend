"""인증 라우터."""

from fastapi import APIRouter, BackgroundTasks, Cookie, Depends, Query, Request, Response
from sqlalchemy.orm import Session

from fastapi.responses import JSONResponse

from core.config import settings
from core.errors import error_response
from core.security import RESTORE_TOKEN_EXPIRE_SECONDS, create_restore_token, decode_restore_token
from db.session import get_db
from schemas.auth import (
    CheckLoginIdResponse,
    LoginRequest,
    PasswordResetRequest,
    RestoreInfoResponse,
    SignupRequest,
    TokenResponse,
)
from schemas.email_verification import (
    SendCodeRequest,
    VerifyCodeRequest,
    VerifyCodeResponse,
)
from services.auth import account_service, auth_service, email_verification_service
from services.auth.auth_service import AccountWithdrawnError, IssuedTokens
from services.auth.mailer import Mailer, get_mailer, send_safely

router = APIRouter(prefix="/api/auth", tags=["auth"])

REFRESH_COOKIE_NAME = "refresh_token"
# refresh 쿠키는 인증 경로에서만 전송되도록 제한한다.
REFRESH_COOKIE_PATH = "/api/auth"


def set_refresh_cookie(response: Response, token: str) -> None:
    """refresh 토큰을 httpOnly 쿠키로 내려준다. (카카오 로그인도 같은 쿠키를 쓴다)"""
    response.set_cookie(
        REFRESH_COOKIE_NAME,
        token,
        max_age=settings.refresh_token_expire_days * 24 * 60 * 60,
        path=REFRESH_COOKIE_PATH,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
    )


RESTORE_COOKIE_NAME = "restore_token"


def set_restore_cookie(response: Response, user_id: int) -> None:
    """탈퇴 유예 중인 계정의 복구 토큰을 짧은 수명의 httpOnly 쿠키로 내려준다. (카카오 로그인도 쓴다)"""
    response.set_cookie(
        RESTORE_COOKIE_NAME,
        create_restore_token(user_id),
        max_age=RESTORE_TOKEN_EXPIRE_SECONDS,
        path=REFRESH_COOKIE_PATH,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
    )


def _token_response(response: Response, tokens: IssuedTokens) -> TokenResponse:
    set_refresh_cookie(response, tokens.refresh_token)
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
) -> TokenResponse | JSONResponse:
    """아이디와 비밀번호로 로그인한다. 탈퇴 유예 중이면 403 ACCOUNT_WITHDRAWN과 복구용 쿠키를 내려준다."""
    try:
        tokens = auth_service.login(db, request)
    except AccountWithdrawnError as withdrawn:
        blocked = error_response(
            403, "ACCOUNT_WITHDRAWN", "탈퇴 처리된 계정입니다. 복구할 수 있어요."
        )
        set_restore_cookie(blocked, withdrawn.user_id)
        return blocked
    return _token_response(response, tokens)


@router.get("/restore", response_model=RestoreInfoResponse)
def restore_info(
    restore_token: str | None = Cookie(default=None), db: Session = Depends(get_db)
) -> RestoreInfoResponse:
    """복구 화면에 보여줄 탈퇴 일정(탈퇴 시각, 삭제 예정 시각)을 반환한다."""
    info = account_service.get_restore_info(db, decode_restore_token(restore_token))
    return RestoreInfoResponse(withdrawn_at=info.withdrawn_at, purge_at=info.purge_at)


@router.post("/restore", response_model=TokenResponse)
def restore(
    response: Response,
    restore_token: str | None = Cookie(default=None),
    db: Session = Depends(get_db),
) -> TokenResponse:
    """탈퇴 유예 중인 계정을 복구하고 로그인 처리한다."""
    tokens = account_service.restore(db, decode_restore_token(restore_token))
    response.delete_cookie(RESTORE_COOKIE_NAME, path=REFRESH_COOKIE_PATH)
    return _token_response(response, tokens)


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


@router.post("/email/send-code", status_code=204)
def send_email_code(
    body: SendCodeRequest,
    request: Request,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    mailer: Mailer = Depends(get_mailer),
) -> None:
    """이메일 인증 코드를 발송한다. 계정 존재 여부와 상관없이 같은 응답을 반환한다."""
    ip = request.client.host if request.client else None
    mail = email_verification_service.send_code(db, body.email, body.purpose, ip)
    if mail is not None:
        # 응답 이후에 보내서, 발송 시간 차이로 계정 존재 여부가 드러나지 않게 한다.
        background_tasks.add_task(send_safely, mailer, mail)


@router.post("/email/verify-code", response_model=VerifyCodeResponse)
def verify_email_code(
    body: VerifyCodeRequest, db: Session = Depends(get_db)
) -> VerifyCodeResponse:
    """인증 코드를 검증하고 가입·비밀번호 재설정에 쓸 토큰을 발급한다."""
    token, expires_in = email_verification_service.verify_code(
        db, body.email, body.purpose, body.code
    )
    return VerifyCodeResponse(email_verification_token=token, expires_in=expires_in)


@router.post("/password/reset", status_code=204)
def reset_password(body: PasswordResetRequest, db: Session = Depends(get_db)) -> None:
    """이메일 인증 후 비밀번호를 재설정한다."""
    auth_service.reset_password(db, body)
