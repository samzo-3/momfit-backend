"""회원 탈퇴(유예 기간 후 삭제), 복구, 만료 계정 삭제 비즈니스 로직.

탈퇴하면 계정을 바로 지우지 않고 status를 withdrawn으로 바꾼 채 데이터를 그대로 둔다.
유예 기간(ACCOUNT_GRACE_DAYS, 기본 30일) 안에는 로그인해서 복구할 수 있고, 기간이 지나면 완전히 삭제한다.
"""

import logging
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from core.clock import utc_now
from core.config import settings
from core.errors import AppError
from models.auth_identity import KAKAO_PROVIDER
from models.user import STATUS_ACTIVE, STATUS_WITHDRAWN, User
from repositories import (
    email_verification_repository,
    refresh_token_repository,
    user_repository,
)
from services import kakao_auth_service
from services.auth_service import IssuedTokens, issue_tokens
from services.kakao_client import KakaoClient

logger = logging.getLogger(__name__)


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


def purge_expired(db: Session, now: datetime | None = None) -> int:
    """유예 기간이 지난 탈퇴 계정을 완전히 삭제하고 삭제한 수를 반환한다.

    사용자 프로필과 건강정보, 로그인 수단, refresh 토큰, 이메일 인증 기록을 모두 지운다.
    같은 작업을 여러 번 실행해도 안전하다.
    """
    now = now or utc_now()
    cutoff = now - timedelta(days=settings.account_grace_days)
    count = 0
    for user in user_repository.list_withdrawn_before(db, cutoff):
        refresh_token_repository.delete_all_for_user(db, user.id)
        if user.email:
            email_verification_repository.delete_by_email(db, user.email)
        user_repository.delete(db, user)
        count += 1
    db.commit()
    return count


def run_purge() -> int:
    """자체 DB 세션으로 만료 계정을 삭제한다. 주기 작업과 수동 실행 스크립트가 함께 쓴다."""
    from db.session import SessionLocal

    with SessionLocal() as db:
        count = purge_expired(db)
    if count:
        logger.info("유예 기간이 지난 탈퇴 계정 %d건을 삭제했습니다.", count)
    return count
