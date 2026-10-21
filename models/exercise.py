"""운동 기본 정보 ORM."""

from sqlalchemy import BigInteger, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from db.base import Base


class Exercise(Base):
    __tablename__ = "exercises"

    id: Mapped[int] = mapped_column(
        BigInteger,
        primary_key=True,
        autoincrement=True,
    )

    exercise_name: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
    )

    target_reps: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    video_url: Mapped[str | None] = mapped_column(
        String(500),
        nullable=True,
    )

    description: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )
