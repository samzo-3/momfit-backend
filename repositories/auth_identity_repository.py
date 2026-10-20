"""auth_identities 테이블 접근."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from models.auth_identity import LOCAL_PROVIDER, AuthIdentity


def add(db: Session, identity: AuthIdentity) -> AuthIdentity:
    """로그인 수단을 추가한다."""
    db.add(identity)
    db.flush()
    return identity


def get_local_by_login_id(db: Session, login_id: str) -> AuthIdentity | None:
    """로컬 로그인 수단을 login_id로 조회한다."""
    return db.scalar(
        select(AuthIdentity).where(
            AuthIdentity.provider == LOCAL_PROVIDER,
            AuthIdentity.login_id == login_id,
        )
    )


def get_by_provider(
    db: Session, provider: str, provider_user_id: str
) -> AuthIdentity | None:
    """provider와 그 provider의 사용자 id로 로그인 수단을 조회한다."""
    return db.scalar(
        select(AuthIdentity).where(
            AuthIdentity.provider == provider,
            AuthIdentity.provider_user_id == provider_user_id,
        )
    )


def get_local_by_user_id(db: Session, user_id: int) -> AuthIdentity | None:
    """사용자의 로컬 로그인 수단을 조회한다."""
    return db.scalar(
        select(AuthIdentity).where(
            AuthIdentity.provider == LOCAL_PROVIDER,
            AuthIdentity.user_id == user_id,
        )
    )
