"""사용자 라우터."""

from fastapi import APIRouter, Depends

from api.deps import get_current_user
from models.user import User
from schemas.user import UserResponse
from services.user_service import to_user_response

router = APIRouter(prefix="/api/users", tags=["users"])


@router.get("/me", response_model=UserResponse)
def read_me(user: User = Depends(get_current_user)) -> UserResponse:
    """내 프로필과 온보딩 상태를 반환한다."""
    return to_user_response(user)
