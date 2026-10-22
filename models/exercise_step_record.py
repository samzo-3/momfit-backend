"""사용자 운동 스텝 수행 기록 모델."""

from decimal import Decimal
from typing import TYPE_CHECKING, Any

from sqlalchemy import BigInteger, ForeignKey, JSON, Numeric, String, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from db.base import Base
from db.types import BigIntId
from models.timestamp_mixin import TimestampMixin

if TYPE_CHECKING:
    from models.exercise import Exercise
    from models.exercise_step import ExerciseStep
    from models.user import User


EXERCISE_RECORD_IN_PROGRESS = "in_progress"
EXERCISE_RECORD_COMPLETED = "completed"


class ExerciseStepRecord(TimestampMixin, Base):
    """사용자가 한 운동 스텝을 수행한 중간 기록과 분석 결과."""

    __tablename__ = "exercise_step_records"

    id: Mapped[int] = mapped_column(
        BigInteger, primary_key=True, autoincrement=True
    )

    user_id: Mapped[int] = mapped_column(
        BigIntId, ForeignKey("users.id"), index=True
    )

    exercise_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("exercises.id"), index=True
    )

    exercise_step_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("exercise_steps.id"), index=True
    )

    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default=EXERCISE_RECORD_IN_PROGRESS,
        server_default=text("'in_progress'"),
    )

    step_score: Mapped[Decimal | None] = mapped_column(
        Numeric(5, 2)
    )

    step_report: Mapped[dict[str, Any] | None] = mapped_column(JSON)

    user: Mapped["User"] = relationship(
        back_populates="exercise_step_records"
    )

    exercise: Mapped["Exercise"] = relationship(
        back_populates="step_records"
    )

    exercise_step: Mapped["ExerciseStep"] = relationship(
        back_populates="records"
    )