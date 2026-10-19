"""refresh_tokens 테이블 접근."""

from datetime import datetime

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from models.refresh_token import RefreshToken


def add(db: Session, token: RefreshToken) -> RefreshToken:
    """refresh 토큰을 저장한다."""
    db.add(token)
    db.flush()
    return token


def get_by_hash_for_update(db: Session, token_hash: str) -> RefreshToken | None:
    """해시로 조회하며 행을 잠가, 같은 토큰으로 동시에 교체되는 것을 막는다."""
    return db.scalar(
        select(RefreshToken)
        .where(RefreshToken.token_hash == token_hash)
        .with_for_update()
    )


def revoke_family(db: Session, family_id: str, now: datetime) -> None:
    """family에 속한 아직 폐기되지 않은 토큰을 모두 폐기한다."""
    db.execute(
        update(RefreshToken)
        .where(RefreshToken.family_id == family_id, RefreshToken.revoked_at.is_(None))
        .values(revoked_at=now)
    )


def revoke_all_for_user(db: Session, user_id: int, now: datetime) -> None:
    """사용자의 아직 폐기되지 않은 refresh 토큰을 모두 폐기한다. 비밀번호 재설정·탈퇴 때 쓴다."""
    db.execute(
        update(RefreshToken)
        .where(RefreshToken.user_id == user_id, RefreshToken.revoked_at.is_(None))
        .values(revoked_at=now)
    )
