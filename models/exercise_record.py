"""사용자 운동 수행 기록 모델."""

from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from db.base import Base
from models.timestamp_mixin import TimestampMixin

if TYPE_CHECKING:
    from models.exercise import Exercise
    from models.exercise_criteria_version import ExerciseCriteriaVersion
    from models.user import User


EXERCISE_RECORD_IN_PROGRESS = "in_progress"
EXERCISE_RECORD_PAUSED = "paused"
EXERCISE_RECORD_RESUMED = "resumed"
EXERCISE_RECORD_COMPLETED = "completed"


class ExerciseRecord(TimestampMixin, Base):
    """사용자의 운동 모드 수행 기록."""

    __tablename__ = "exercise_records"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    exercise_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("exercises.id"), index=True)
    exercise_criteria_version_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("exercise_criteria_versions.id"), index=True
    )
    total_score: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    status: Mapped[str] = mapped_column(
        String(20),
        default=EXERCISE_RECORD_IN_PROGRESS,
        server_default=EXERCISE_RECORD_IN_PROGRESS,
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime)
    is_completed: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("0")
    )
    completed_sets: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default=text("0")
    )

    user: Mapped["User"] = relationship(back_populates="exercise_records")
    exercise: Mapped["Exercise"] = relationship(back_populates="records")
    exercise_criteria_version: Mapped["ExerciseCriteriaVersion"] = relationship(back_populates="records")
