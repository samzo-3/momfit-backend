"""사용자 라우터."""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from api.deps import get_current_user
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

