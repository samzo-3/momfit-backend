"""사용자 프로필 모델."""

from datetime import date, datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, Date, DateTime, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from core.clock import utc_now
from db.base import Base

if TYPE_CHECKING:
    from models.auth_identity import AuthIdentity


class User(Base):
    """사용자 프로필. 로그인 수단은 AuthIdentity가 가진다."""

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    nickname: Mapped[str] = mapped_column(String(50))
    # 로컬 가입자만 가진다. 카카오 가입자는 NULL (MySQL unique는 NULL 중복을 허용한다).
    email: Mapped[str | None] = mapped_column(String(255), unique=True)
    due_date: Mapped[date | None] = mapped_column(Date)
    exercise_level: Mapped[str | None] = mapped_column(String(10))
    onboarding_completed: Mapped[bool] = mapped_column(Boolean, default=False)
    terms_agreed_at: Mapped[datetime | None] = mapped_column(DateTime)
    health_data_agreed_at: Mapped[datetime | None] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)

    identities: Mapped[list["AuthIdentity"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )

