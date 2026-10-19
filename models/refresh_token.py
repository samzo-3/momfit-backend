"""refresh 토큰 모델. 원문은 저장하지 않고 해시만 저장한다."""

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from core.clock import utc_now
from db.base import Base


class RefreshToken(Base):
    """로그인 한 번(family) 안에서 교체(rotation)되는 refresh 토큰."""

    __tablename__ = "refresh_tokens"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    # 같은 로그인에서 교체된 토큰들을 묶는다. 재사용이 탐지되면 family 전체를 폐기한다.
    family_id: Mapped[str] = mapped_column(String(36), index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
