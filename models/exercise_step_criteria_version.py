"""운동 STEP별 평가 기준 버전 ORM."""

from datetime import datetime
from typing import Any

from sqlalchemy import BigInteger, DateTime, ForeignKey, JSON, String
from sqlalchemy.orm import Mapped, mapped_column

from core.clock import utc_now
from db.base import Base


class ExerciseStepCriteriaVersion(Base):
    __tablename__ = "exercise_step_criteria_versions"

    id: Mapped[int] = mapped_column(
        BigInteger,
        primary_key=True,
        autoincrement=True,
    )

    exercise_step_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("exercise_steps.id"),
        nullable=False,
    )

    exercise_criteria_version_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("exercise_criteria_versions.id"),
        nullable=False,
    )

    evaluation_criteria: Mapped[dict[str, Any]] = mapped_column(
        JSON,
        nullable=False,
    )

    step_criteria_version: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        default=utc_now,
    )
