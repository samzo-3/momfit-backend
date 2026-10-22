"""사용자 라우터."""

from fastapi import APIRouter, Depends, Response
from sqlalchemy.orm import Session

from api.deps import get_current_user
from api.auth import REFRESH_COOKIE_NAME, REFRESH_COOKIE_PATH
from db.session import get_db
from models.user import User
from schemas.user import OnboardingRequest, UpdateProfileRequest, UserResponse
from services.auth import account_service
from services.user import user_service
from services.auth.kakao_client import KakaoClient, get_kakao_client
from services.user.user_service import to_user_response

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


@router.post("/me/onboarding", response_model=UserResponse)
def complete_onboarding(
    body: OnboardingRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> UserResponse:
    """카카오로 처음 가입한 사용자의 동의와 초기 프로필을 제출한다."""
    return user_service.complete_onboarding(db, user, body)


@router.delete("/me", status_code=204)
def delete_me(
    response: Response,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    kakao_client: KakaoClient = Depends(get_kakao_client),
) -> None:
    """회원을 탈퇴 처리하고 이 기기의 refresh 쿠키를 삭제한다. 카카오 계정은 연결도 끊는다. 관리자는 403.

    계정은 바로 지워지지 않고 유예 기간(기본 30일) 동안 복구할 수 있다. 기간이 지나면 완전히 삭제된다.
    """
    account_service.withdraw(db, user, kakao_client)
    response.delete_cookie(REFRESH_COOKIE_NAME, path=REFRESH_COOKIE_PATH)
