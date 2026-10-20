"""회원 탈퇴(유예 기간 후 삭제)와 복구 비즈니스 로직.

탈퇴하면 계정을 바로 지우지 않고 status를 withdrawn으로 바꾼 채 데이터를 그대로 둔다.
유예 기간(ACCOUNT_GRACE_DAYS, 기본 30일) 안에는 로그인해서 복구할 수 있고, 기간이 지나면 완전히 삭제한다.
"""

import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from core.clock import utc_now
from core.config import settings
from core.errors import AppError
from models.auth_identity import KAKAO_PROVIDER
from models.user import STATUS_ACTIVE, STATUS_WITHDRAWN, User
from repositories import refresh_token_repository, user_repository
from services import kakao_auth_service
from services.auth_service import IssuedTokens, issue_tokens
from services.kakao_client import KakaoClient


@dataclass(frozen=True)
class RestoreInfo:
    """복구 화면에 보여줄 탈퇴 일정. 시각은 UTC 기준(tz 포함)이다."""

    withdrawn_at: datetime
    purge_at: datetime


def _utc(value: datetime) -> datetime:
    return value.replace(tzinfo=timezone.utc)


def purge_at(withdrawn_at: datetime) -> datetime:
    """탈퇴 요청 시각에서 유예 기간이 지나 삭제되는 시각."""
    return withdrawn_at + timedelta(days=settings.account_grace_days)


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


def _withdrawn_user(db: Session, user_id: int, now: datetime) -> User:
    """복구할 수 있는 탈퇴 유예 중인 사용자를 돌려준다. 아니면 RESTORE_INVALID."""
    user = user_repository.get_by_id(db, user_id)
    if (
        user is None
        or user.status != STATUS_WITHDRAWN
        or user.withdrawn_at is None
        or purge_at(user.withdrawn_at) <= now
    ):
        raise AppError(
            401, "RESTORE_INVALID", "복구할 수 없는 계정입니다. 복구 가능 기간이 지났을 수 있어요."
        )
    return user


def get_restore_info(db: Session, user_id: int, now: datetime | None = None) -> RestoreInfo:
    """복구 화면에 보여줄 탈퇴 일정을 조회한다."""
    user = _withdrawn_user(db, user_id, now or utc_now())
    assert user.withdrawn_at is not None
    return RestoreInfo(
        withdrawn_at=_utc(user.withdrawn_at), purge_at=_utc(purge_at(user.withdrawn_at))
    )


def restore(db: Session, user_id: int, now: datetime | None = None) -> IssuedTokens:
    """탈퇴 유예 중인 계정을 되살리고 로그인 처리한다."""
    now = now or utc_now()
    user = _withdrawn_user(db, user_id, now)
    user.status = STATUS_ACTIVE
    user.withdrawn_at = None
    tokens = issue_tokens(db, user.id, str(uuid.uuid4()), now)
    db.commit()
    return tokens
