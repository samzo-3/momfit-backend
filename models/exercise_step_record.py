"""자세히 배우기 모드의 STEP별 수행 기록."""

from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    BigInteger,
    DateTime,
    ForeignKey,
    JSON,
    Numeric,
    String,
)
from sqlalchemy.orm import Mapped, mapped_column

from core.clock import utc_now
from db.base import Base
from models.user import User


class ExerciseStepRecord(Base):
    __tablename__ = "exercise_step_records"

    id: Mapped[int] = mapped_column(
        BigInteger,
        primary_key=True,
        autoincrement=True,
    )

    user_id: Mapped[int] = mapped_column(
        User.__table__.c.id.type.copy(),
        ForeignKey("users.id"),
        nullable=False,
    )

    exercise_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("exercises.id"),
        nullable=False,
    )

    exercise_step_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("exercise_steps.id"),
        nullable=False,
    )

    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
    )

    step_score: Mapped[Decimal | None] = mapped_column(
        Numeric(5, 2),
        nullable=True,
    )

    step_report: Mapped[dict[str, Any] | None] = mapped_column(
        JSON,
        nullable=True,
    )

    modified_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        default=utc_now,
        onupdate=utc_now,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        default=utc_now,
    )
