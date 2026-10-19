"""users 테이블 접근."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from models.user import User


def add(db: Session, user: User) -> User:
    """사용자를 추가하고 id를 확정한다."""
    db.add(user)
    db.flush()
    return user


def get_by_id(db: Session, user_id: int) -> User | None:
    """id로 사용자를 조회한다."""
    return db.get(User, user_id)


def get_by_email(db: Session, email: str) -> User | None:
    """이메일로 사용자를 조회한다."""
    return db.scalar(select(User).where(User.email == email))


def delete(db: Session, user: User) -> None:
    """사용자를 삭제한다. 로그인 수단(auth_identities)은 ORM cascade로 함께 삭제된다."""
    db.delete(user)
