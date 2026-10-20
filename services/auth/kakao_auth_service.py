"""카카오 로그인(가입·로그인)과 연결 해제 비즈니스 로직."""

import logging
import uuid
from datetime import datetime

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from core.clock import utc_now
from models.auth_identity import KAKAO_PROVIDER, AuthIdentity
from models.user import STATUS_ACTIVE, User
from repositories import auth_identity_repository, user_repository
from services.auth.auth_service import AccountWithdrawnError, IssuedTokens, issue_tokens
from services.auth.kakao_client import KakaoClient, KakaoError, KakaoProfile

logger = logging.getLogger(__name__)

DEFAULT_NICKNAME = "카카오 사용자"
MAX_NICKNAME_LENGTH = 20


def _initial_nickname(profile: KakaoProfile) -> str:
    nickname = (profile.nickname or "").strip()[:MAX_NICKNAME_LENGTH]
    return nickname or DEFAULT_NICKNAME


def login_with_kakao(
    db: Session, profile: KakaoProfile, now: datetime | None = None
) -> IssuedTokens:
    """카카오 회원번호로 로그인한다. 처음이면 계정을 만들고 온보딩 전 상태로 둔다.

    수집하는 값은 회원번호와 닉네임뿐이다. 이미 가입한 사용자의 닉네임은 덮어쓰지 않는다.
    """
    now = now or utc_now()
    identity = auth_identity_repository.get_by_provider(db, KAKAO_PROVIDER, profile.id)
    if identity is None:
        try:
            user = user_repository.add(
                db, User(nickname=_initial_nickname(profile), onboarding_completed=False)
            )
            identity = auth_identity_repository.add(
                db,
                AuthIdentity(
                    user_id=user.id,
                    provider=KAKAO_PROVIDER,
                    provider_user_id=profile.id,
                ),
            )
        except IntegrityError:
            # 같은 카카오 계정으로 동시에 처음 로그인한 요청이 먼저 가입을 마친 경우
            db.rollback()
            identity = auth_identity_repository.get_by_provider(
                db, KAKAO_PROVIDER, profile.id
            )
            if identity is None:
                raise

    user = user_repository.get_by_id(db, identity.user_id)
    if user is not None and user.status != STATUS_ACTIVE:
        # 탈퇴 유예 중인 계정이다. 카카오 인증은 끝났으니 복구 안내로 넘긴다.
        db.commit()
        raise AccountWithdrawnError(user.id)

    tokens = issue_tokens(db, identity.user_id, str(uuid.uuid4()), now)
    db.commit()
    return tokens


def unlink_best_effort(client: KakaoClient, kakao_user_id: str) -> None:
    """회원 탈퇴 뒤 카카오 연결을 끊는다. 실패해도 탈퇴는 이미 끝났으므로 로그만 남긴다.

    사용자가 카카오 계정 설정에서 직접 연결을 끊을 수 있다.
    """
    try:
        client.unlink(kakao_user_id)
    except KakaoError as error:
        logger.warning("카카오 연결 해제에 실패했습니다: %s", error)
    except Exception:
        logger.warning("카카오 연결 해제 중 예상하지 못한 오류가 발생했습니다.")
