"""여러 ORM 모델이 공유하는 컬럼 Mixin."""

from datetime import datetime

from sqlalchemy import DateTime
from sqlalchemy.orm import Mapped, mapped_column

from core.clock import utc_now


class CreatedAtMixin:
    """생성 시각만 기록하는 테이블용 Mixin."""

    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)


class TimestampMixin(CreatedAtMixin):
    """생성·수정 시각을 모두 기록하는 테이블용 Mixin."""

    modified_at: Mapped[datetime] = mapped_column(
        DateTime, default=utc_now, onupdate=utc_now
    )