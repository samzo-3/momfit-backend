"""일반 운동 수행 기록."""
from datetime import datetime
from decimal import Decimal

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, Integer, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column

from core.clock import utc_now
from db.base import Base
from models.user import User


class ExerciseRecord(Base):
    __tablename__ = "exercise_records"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        User.__table__.c.id.type.copy(),
        ForeignKey("users.id"),
        nullable=False,
    )
    exercise_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("exercises.id"), nullable=False
    )
    exercise_criteria_version_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("exercise_criteria_versions.id"),
        nullable=False,
    )
    completed_sets: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    total_score: Mapped[Decimal] = mapped_column(
        Numeric(6, 2), nullable=False, default=0
    )
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="IN_PROGRESS"
    )
    started_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=utc_now
    )
    ended_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    is_completed: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=utc_now
    )
    modified_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=utc_now, onupdate=utc_now
    )
