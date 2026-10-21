"""운동별 STEP 정의 ORM."""

from sqlalchemy import BigInteger, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from db.base import Base


class ExerciseStep(Base):
    __tablename__ = "exercise_steps"

    id: Mapped[int] = mapped_column(
        BigInteger,
        primary_key=True,
        autoincrement=True,
    )

    exercise_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("exercises.id"),
        nullable=False,
    )

    step_order: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    step_name: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )

    clip_video_url: Mapped[str | None] = mapped_column(
        String(500),
        nullable=True,
    )

    step_description: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )
