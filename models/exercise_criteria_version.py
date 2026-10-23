"""운동 평가 기준 버전 모델."""

from typing import TYPE_CHECKING, Any

from sqlalchemy import BigInteger, ForeignKey, Integer, JSON, String, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from db.base import Base
from models.timestamp_mixin import CreatedAtMixin


if TYPE_CHECKING:
    from models.exercise import Exercise
    from models.exercise_record import ExerciseRecord
    from models.exercise_step_record import ExerciseStepRecord
    from models.exercise_step_criteria_version import ExerciseStepCriteriaVersion


CRITERIA_STATUS_DRAFT = "DRAFT"
CRITERIA_STATUS_ACTIVE = "ACTIVE"
CRITERIA_STATUS_ARCHIVED = "ARCHIVED"


class ExerciseCriteriaVersion(CreatedAtMixin, Base):
    """운동 모드 전체를 평가하는 기준의 버전."""

    __tablename__ = "exercise_criteria_versions"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    exercise_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("exercises.id"), index=True)
    evaluation_criteria: Mapped[dict[str, Any]] = mapped_column(JSON)
    criteria_version: Mapped[str] = mapped_column(String(100))
    schema_version: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(
        String(20),
        default=CRITERIA_STATUS_ACTIVE,
        server_default=text("'ACTIVE'"),
    )

    exercise: Mapped["Exercise"] = relationship(back_populates="criteria_versions")
    step_criteria_versions: Mapped[list["ExerciseStepCriteriaVersion"]] = relationship(back_populates="exercise_criteria_version")
    records: Mapped[list["ExerciseRecord"]] = relationship(back_populates="exercise_criteria_version")
    step_records: Mapped[list["ExerciseStepRecord"]] = relationship(
        back_populates="exercise_criteria_version"
    )
