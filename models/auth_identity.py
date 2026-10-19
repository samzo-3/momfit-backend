"""사용자의 로그인 수단(로컬, 카카오 등) 모델."""

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from core.clock import utc_now
from db.base import Base

if TYPE_CHECKING:
    from models.user import User

LOCAL_PROVIDER = "local"


class AuthIdentity(Base):
    """provider별 로그인 수단. 로컬은 login_id와 password_hash를 가진다."""

    __tablename__ = "auth_identities"
    __table_args__ = (UniqueConstraint("provider", "provider_user_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    provider: Mapped[str] = mapped_column(String(20))
    # 로컬은 소문자로 정규화한 login_id, 소셜은 provider가 준 사용자 id
    provider_user_id: Mapped[str] = mapped_column(String(100))
    login_id: Mapped[str | None] = mapped_column(String(20), unique=True)
    password_hash: Mapped[str | None] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)

    user: Mapped["User"] = relationship(back_populates="identities")
