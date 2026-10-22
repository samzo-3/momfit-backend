"""이메일 인증 코드 모델. 코드 원문은 저장하지 않고 해시만 저장한다."""

from datetime import datetime

from sqlalchemy import DateTime, Index, String
from sqlalchemy.orm import Mapped, mapped_column

from db.base import Base
from db.types import BigIntId
from models.timestamp_mixin import CreatedAtMixin


class EmailVerification(CreatedAtMixin, Base):
    """발송한 인증 코드 한 건. 발송 제한(횟수·간격)의 기록도 겸한다."""

    __tablename__ = "email_verifications"
    __table_args__ = (
        Index("ix_email_verifications_email_purpose", "email", "purpose"),
        # 발송 간격·횟수 제한 쿼리가 created_at으로 정렬·필터하므로 믹스인 컬럼에 인덱스를 따로 건다.
        Index("ix_email_verifications_created_at", "created_at"),
    )

    id: Mapped[int] = mapped_column(
        BigIntId, primary_key=True, autoincrement=True
    )
    email: Mapped[str] = mapped_column(String(255))
    purpose: Mapped[str] = mapped_column(String(20))
    code_hash: Mapped[str] = mapped_column(String(64))
    # 요청한 클라이언트 IP. IP별 발송 제한에 쓴다. (IPv6 최대 45자)
    ip: Mapped[str | None] = mapped_column(String(45), index=True)
    attempts: Mapped[int] = mapped_column(default=0)
    expires_at: Mapped[datetime] = mapped_column(DateTime)
    # 검증에 성공했거나, 새 코드로 대체되었거나, 시도 횟수를 넘겨 무효화된 시각
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime)
