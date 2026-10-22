"""관리자 라우터. 모든 라우트는 관리자만 호출할 수 있다."""

from fastapi import APIRouter, Depends

from api.deps import require_admin
from models.user import User
from schemas.user import UserResponse
from services.user.user_service import to_user_response

router = APIRouter(prefix="/api/admin", tags=["admin"])


@router.get("/me", response_model=UserResponse)
def read_admin_me(admin: User = Depends(require_admin)) -> UserResponse:
    """관리자 본인의 프로필. 프론트가 관리자 화면 진입 가능 여부를 서버 기준으로 확인하는 데 쓴다."""
    return to_user_response(admin)
