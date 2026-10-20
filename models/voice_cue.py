"""운동 및 사용자 추적 음성 안내 ORM 모델."""

from datetime import datetime

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from core.clock import utc_now
from db.base import Base


class VoiceCue(Base):
    """운동 모드, STEP 학습, 사용자 추적에 사용할 음성 안내."""

    __tablename__ = "voice_cues"

    id: Mapped[int] = mapped_column(
        BigInteger,
        primary_key=True,
        autoincrement=True,
    )

    exercise_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("exercises.id"),
        nullable=True,
    )

    exercise_step_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("exercise_steps.id"),
        nullable=True,
    )

    category: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
    )

    event_code: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
    )

    audio_url: Mapped[str] = mapped_column(
        String(500),
        nullable=False,
    )

    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
    )

    message: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        default=utc_now,
    )

    modified_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        default=utc_now,
        onupdate=utc_now,
    )
