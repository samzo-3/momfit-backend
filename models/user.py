"""사용자 프로필 모델."""

from datetime import date, datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, Date, DateTime, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from db.base import Base
from db.types import BigIntId
from models.timestamp_mixin import TimestampMixin

if TYPE_CHECKING:
    from models.auth_identity import AuthIdentity
    from models.exercise_record import ExerciseRecord
    from models.exercise_step_record import ExerciseStepRecord
    from models.user_goal import UserGoal


STATUS_ACTIVE = "active"
STATUS_WITHDRAWN = "withdrawn"

ROLE_USER = "user"
ROLE_ADMIN = "admin"


class User(TimestampMixin, Base):
    """사용자 프로필. 로그인 수단은 AuthIdentity가 가진다.

    modified_at은 회원정보를 마지막으로 수정한 시각이다. users 행이 UPDATE될 때마다 갱신된다.
    (로그인·토큰 갱신처럼 users를 건드리지 않는 동작은 갱신하지 않는다.)
    """

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(
        BigIntId, primary_key=True, autoincrement=True
    )
    nickname: Mapped[str] = mapped_column(String(50))
    # 로컬 가입자만 가진다. 카카오 가입자는 NULL (MySQL unique는 NULL 중복을 허용한다).
    email: Mapped[str | None] = mapped_column(String(255), unique=True)
    due_date: Mapped[date | None] = mapped_column(Date)
    exercise_level: Mapped[str | None] = mapped_column(String(10))
    onboarding_completed: Mapped[bool] = mapped_column(Boolean, default=False)
    terms_agreed_at: Mapped[datetime | None] = mapped_column(DateTime)
    health_data_agreed_at: Mapped[datetime | None] = mapped_column(DateTime)
    # active: 이용 중 / withdrawn: 탈퇴 유예 중(로그인할 수 없고, 유예 기간이 지나면 완전히 삭제된다)
    status: Mapped[str] = mapped_column(
        String(20), default=STATUS_ACTIVE, server_default=STATUS_ACTIVE
    )
    # 탈퇴를 요청한 시각. 이 시각에서 유예 기간이 지나면 삭제 대상이 된다. 복구하면 NULL로 돌아간다.
    withdrawn_at: Mapped[datetime | None] = mapped_column(DateTime)
    # user: 일반 회원 / admin: 관리자. 가입 API로는 지정할 수 없고 DB에서 직접 바꾼다.
    role: Mapped[str] = mapped_column(
        String(20), default=ROLE_USER, server_default=ROLE_USER
    )

    identities: Mapped[list["AuthIdentity"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )

    exercise_records: Mapped[list["ExerciseRecord"]] = relationship(
        back_populates="user"
    )

    exercise_step_records: Mapped[list["ExerciseStepRecord"]] = relationship(
        back_populates="user"
    )

    exercise_goals: Mapped[list["UserGoal"]] = relationship(
        back_populates="user"
    )

