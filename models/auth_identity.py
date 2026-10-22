"""사용자의 로그인 수단(로컬, 카카오 등) 모델."""

from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from db.base import Base
from db.types import BigIntId
from models.timestamp_mixin import CreatedAtMixin

if TYPE_CHECKING:
    from models.user import User

LOCAL_PROVIDER = "local"
KAKAO_PROVIDER = "kakao"


class AuthIdentity(CreatedAtMixin, Base):
    """provider별 로그인 수단. 로컬은 login_id와 password_hash를 가진다."""

    __tablename__ = "auth_identities"
    __table_args__ = (UniqueConstraint("provider", "provider_user_id"),)

    id: Mapped[int] = mapped_column(
        BigIntId, primary_key=True, autoincrement=True
    )
    user_id: Mapped[int] = mapped_column(
        BigIntId, ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    provider: Mapped[str] = mapped_column(String(20))
    # 로컬은 소문자로 정규화한 login_id, 소셜은 provider가 준 사용자 id
    provider_user_id: Mapped[str] = mapped_column(String(100))
    login_id: Mapped[str | None] = mapped_column(String(20), unique=True)
    password_hash: Mapped[str | None] = mapped_column(String(255))

    user: Mapped["User"] = relationship(back_populates="identities")
