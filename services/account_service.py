"""회원 탈퇴(유예 기간 후 삭제) 비즈니스 로직.

탈퇴하면 계정을 바로 지우지 않고 status를 withdrawn으로 바꾼 채 데이터를 그대로 둔다.
유예 기간(ACCOUNT_GRACE_DAYS, 기본 30일) 안에는 로그인해서 복구할 수 있고, 기간이 지나면 완전히 삭제한다.
"""

from datetime import datetime

from sqlalchemy.orm import Session

from core.clock import utc_now
from models.auth_identity import KAKAO_PROVIDER
from models.user import STATUS_WITHDRAWN, User
from repositories import refresh_token_repository
from services import kakao_auth_service
from services.kakao_client import KakaoClient


def withdraw(
    db: Session,
    user: User,
    kakao_client: KakaoClient | None = None,
    now: datetime | None = None,
) -> None:
    """회원을 탈퇴 처리한다. 데이터는 그대로 두고 상태만 바꾸며, 모든 기기의 로그인을 해제한다.

    카카오 계정이면 처리를 마친 뒤 카카오 연결을 끊는다. (실패해도 탈퇴는 유지된다)
    복구하면 카카오에서 다시 동의 화면이 나온다.
    """
    now = now or utc_now()
    kakao_id = next(
        (i.provider_user_id for i in user.identities if i.provider == KAKAO_PROVIDER),
        None,
    )
    user.status = STATUS_WITHDRAWN
    user.withdrawn_at = now
    refresh_token_repository.revoke_all_for_user(db, user.id, now)
    db.commit()

    if kakao_id and kakao_client:
        kakao_auth_service.unlink_best_effort(kakao_client, kakao_id)
