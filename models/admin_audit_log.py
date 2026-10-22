"""관리자 조회·조치 이력 모델."""

from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

from db.base import Base
from db.types import BigIntId
from models.timestamp_mixin import CreatedAtMixin

ACTION_VIEW_MEMBER = "view_member"
ACTION_WITHDRAW_MEMBER = "withdraw_member"
ACTION_RESTORE_MEMBER = "restore_member"


class AdminAuditLog(CreatedAtMixin, Base):
    """누가(관리자) 누구에게(회원) 무엇을 했는지 남긴다.

    회원이 나중에 완전히 삭제돼도 이력은 남아야 하므로 users를 FK로 참조하지 않고,
    id와 함께 그 시점의 닉네임을 같이 저장한다. 수정·삭제하지 않고 추가만 한다.
    """

    __tablename__ = "admin_audit_logs"

    id: Mapped[int] = mapped_column(BigIntId, primary_key=True, autoincrement=True)
    admin_id: Mapped[int] = mapped_column(BigIntId, index=True)
    admin_nickname: Mapped[str] = mapped_column(String(50))
    target_user_id: Mapped[int] = mapped_column(BigIntId, index=True)
    target_nickname: Mapped[str] = mapped_column(String(50))
    action: Mapped[str] = mapped_column(String(30))
