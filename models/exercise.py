"""운동 공통 정보 모델."""

from typing import TYPE_CHECKING

from sqlalchemy import BigInteger, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from db.base import Base

if TYPE_CHECKING:
    from models.exercise_criteria_version import ExerciseCriteriaVersion
    from models.exercise_record import ExerciseRecord
    from models.exercise_step import ExerciseStep
    from models.exercise_step_record import ExerciseStepRecord
    from models.user_goal import UserGoal


class Exercise(Base):
    """운동의 공통 정보와 해당 운동의 스텝·평가 기준을 가진다."""

    __tablename__ = "exercises"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    exercise_name: Mapped[str] = mapped_column(String(50))
    video_url: Mapped[str] = mapped_column(String(500))
    description: Mapped[str | None] = mapped_column(Text)

    steps: Mapped[list["ExerciseStep"]] = relationship(back_populates="exercise")
    criteria_versions: Mapped[list["ExerciseCriteriaVersion"]] = relationship(back_populates="exercise")
    goals: Mapped[list["UserGoal"]] = relationship(back_populates="exercise")
    records: Mapped[list["ExerciseRecord"]] = relationship(back_populates="exercise")
    step_records: Mapped[list["ExerciseStepRecord"]] = relationship(back_populates="exercise")
