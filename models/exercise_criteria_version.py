"""운동별 평가 기준 버전."""
from sqlalchemy import BigInteger, ForeignKey, Integer, Numeric, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from decimal import Decimal

from db.base import Base


class ExerciseCriteriaVersion(Base):
    __tablename__ = "exercise_criteria_versions"
    __table_args__ = (
        UniqueConstraint("exercise_id", "version", name="uq_exercise_criteria_version"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    exercise_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("exercises.id"), nullable=False
    )
    version: Mapped[str] = mapped_column(String(20), nullable=False)
    target_sets: Mapped[int] = mapped_column(Integer, nullable=False)
    score_per_set: Mapped[Decimal] = mapped_column(Numeric(6, 2), nullable=False)
