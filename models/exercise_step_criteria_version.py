"""운동 스텝 평가 기준 버전 모델."""

from typing import TYPE_CHECKING, Any

from sqlalchemy import BigInteger, ForeignKey, JSON, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from db.base import Base
from models.timestamp_mixin import CreatedAtMixin

if TYPE_CHECKING:
    from models.exercise_criteria_version import ExerciseCriteriaVersion
    from models.exercise_step import ExerciseStep


class ExerciseStepCriteriaVersion(CreatedAtMixin, Base):
    """특정 운동 기준 버전에 연결된 스텝별 평가 기준."""

    __tablename__ = "exercise_step_criteria_versions"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    exercise_step_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("exercise_steps.id"), index=True)
    exercise_criteria_version_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("exercise_criteria_versions.id"), index=True
    )
    evaluation_criteria: Mapped[dict[str, Any]] = mapped_column(JSON)
    step_criteria_version: Mapped[str] = mapped_column(String(100))

    exercise_step: Mapped["ExerciseStep"] = relationship(back_populates="criteria_versions")
    exercise_criteria_version: Mapped["ExerciseCriteriaVersion"] = relationship(back_populates="step_criteria_versions")
