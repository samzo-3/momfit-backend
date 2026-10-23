"""운동 스텝 모델."""

from typing import TYPE_CHECKING

from sqlalchemy import BigInteger, Boolean, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from db.base import Base

if TYPE_CHECKING:
    from models.exercise import Exercise
    from models.exercise_step_criteria_version import ExerciseStepCriteriaVersion
    from models.exercise_step_record import ExerciseStepRecord


class ExerciseStep(Base):
    """한 운동을 구성하는 순서 있는 자세 학습 단계."""

    __tablename__ = "exercise_steps"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    exercise_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("exercises.id"), index=True)
    step_order: Mapped[int] = mapped_column(Integer)
    step_name: Mapped[str] = mapped_column(String(100))
    clip_video_url: Mapped[str] = mapped_column(String(500))
    step_description: Mapped[str | None] = mapped_column(Text)
    important: Mapped[bool] = mapped_column(Boolean, nullable=False)

    exercise: Mapped["Exercise"] = relationship(back_populates="steps")
    criteria_versions: Mapped[list["ExerciseStepCriteriaVersion"]] = relationship(back_populates="exercise_step")
    records: Mapped[list["ExerciseStepRecord"]] = relationship(back_populates="exercise_step")
