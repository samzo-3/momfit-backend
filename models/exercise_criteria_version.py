"""일반 운동 평가 기준 버전 ORM — MomFit ERD 기준."""

from datetime import datetime
from typing import Any

from sqlalchemy import BigInteger, DateTime, ForeignKey, Integer, JSON, String
from sqlalchemy.orm import Mapped, mapped_column

from core.clock import utc_now
from db.base import Base


class ExerciseCriteriaVersion(Base):
    __tablename__ = "exercise_criteria_versions"

    id: Mapped[int] = mapped_column(
        BigInteger, primary_key=True, autoincrement=True
    )

    exercise_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("exercises.id"), nullable=False
    )

    evaluation_criteria: Mapped[dict[str, Any]] = mapped_column(
        JSON, nullable=False
    )

    criteria_version: Mapped[str] = mapped_column(
        String(100), nullable=False
    )

    schema_version: Mapped[int] = mapped_column(
        Integer, nullable=False
    )

    status: Mapped[str] = mapped_column(
        String(20), nullable=False
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=utc_now
    )
