"""사용자 운동 목표 모델."""

from typing import TYPE_CHECKING

from sqlalchemy import BigInteger, ForeignKey, Integer
from sqlalchemy.orm import Mapped, mapped_column, relationship

from db.base import Base
from models.timestamp_mixin import CreatedAtMixin

if TYPE_CHECKING:
    from models.exercise import Exercise
    from models.user import User


class UserGoal(CreatedAtMixin, Base):
    """사용자가 선택한 운동과 목표 횟수."""

    __tablename__ = "user_goal"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    exercise_id: Mapped[int] = mapped_column(
        "exercises_id", BigInteger, ForeignKey("exercises.id"), index=True
    )
    count: Mapped[int | None] = mapped_column(Integer)

    user: Mapped["User"] = relationship(back_populates="exercise_goals")
    exercise: Mapped["Exercise"] = relationship(back_populates="goals")
