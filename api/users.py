"""사용자 라우터."""

from fastapi import APIRouter, Depends, Response
from sqlalchemy.orm import Session

from api.deps import get_current_user
from api.auth import REFRESH_COOKIE_NAME, REFRESH_COOKIE_PATH
from db.session import get_db
from models.user import User
from schemas.user import UpdateProfileRequest, UserResponse
from services import user_service
from services.user_service import to_user_response

router = APIRouter(prefix="/api/users", tags=["users"])


@router.get("/me", response_model=UserResponse)
def read_me(user: User = Depends(get_current_user)) -> UserResponse:
    """내 프로필과 온보딩 상태를 반환한다."""
    return to_user_response(user)


@router.patch("/me", response_model=UserResponse)
def update_me(
    body: UpdateProfileRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> UserResponse:
    """닉네임·출산 예정일·운동 경험을 수정한다."""
    return user_service.update_profile(db, user, body)


@router.delete("/me", status_code=204)
def delete_me(
    response: Response,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> None:
    """회원을 탈퇴시키고 이 기기의 refresh 쿠키를 삭제한다."""
    user_service.delete_account(db, user)
    response.delete_cookie(REFRESH_COOKIE_NAME, path=REFRESH_COOKIE_PATH)
