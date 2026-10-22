"""라우터에서 공통으로 쓰는 인증 의존성."""

from fastapi import Depends, Request
from sqlalchemy.orm import Session

from core.errors import AppError
from core.security import decode_access_token
from db.session import get_db
from models.user import ROLE_ADMIN, STATUS_ACTIVE, User
from repositories import user_repository


def get_current_user(request: Request, db: Session = Depends(get_db)) -> User:
    """Authorization: Bearer 헤더의 access 토큰으로 현재 사용자를 조회한다."""
    scheme, _, token = request.headers.get("Authorization", "").partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise AppError(401, "UNAUTHORIZED", "인증이 필요합니다.")
    user = user_repository.get_by_id(db, decode_access_token(token))
    # 탈퇴 유예 중인 계정은 이미 발급된 access 토큰이 남아 있어도 통과시키지 않는다.
    if user is None or user.status != STATUS_ACTIVE:
        raise AppError(401, "UNAUTHORIZED", "인증이 필요합니다.")
    return user


def get_onboarded_user(user: User = Depends(get_current_user)) -> User:
    """온보딩을 마친 사용자만 통과시킨다. /users/me, /auth/* 이외의 보호 API에서 사용한다."""
    if not user.onboarding_completed:
        raise AppError(403, "ONBOARDING_REQUIRED", "온보딩을 먼저 완료해 주세요.")
    return user


def require_admin(user: User = Depends(get_onboarded_user)) -> User:
    """관리자만 통과시킨다. 모든 /api/admin/* 라우트에 적용한다."""
    if user.role != ROLE_ADMIN:
        raise AppError(403, "FORBIDDEN", "관리자만 접근할 수 있습니다.")
    return user
