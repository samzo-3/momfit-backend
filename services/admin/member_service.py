"""관리자 회원관리: 목록·상세 조회와 강제 탈퇴·복구. 모든 조회·조치는 이력으로 남긴다."""

from datetime import date, datetime, timedelta, timezone

from sqlalchemy.orm import Session

from core.clock import today_kst, utc_now
from core.errors import AppError
from models.admin_audit_log import (
    ACTION_RESTORE_MEMBER,
    ACTION_VIEW_MEMBER,
    ACTION_WITHDRAW_MEMBER,
    AdminAuditLog,
)
from models.user import STATUS_ACTIVE, STATUS_WITHDRAWN, User
from repositories import admin_member_repository as repo
from schemas.admin import (
    MemberDetail,
    MemberHistory,
    MemberListItem,
    MemberListResponse,
    MemberRecord,
)
from services.auth import account_service
from services.auth.kakao_client import KakaoClient

MAX_PAGE_SIZE = 50
RECENT_RECORDS = 10
HISTORY_LIMIT = 20


def _aware(value: datetime | None) -> datetime | None:
    """DB의 naive UTC 시각에 UTC 표시를 붙인다."""
    return value.replace(tzinfo=timezone.utc) if value else None


def _not_found() -> AppError:
    return AppError(404, "MEMBER_NOT_FOUND", "회원을 찾을 수 없습니다.")


def _item_fields(
    user: User, last_visit: date | None, completed: int
) -> dict[str, object]:
    identity = user.identities[0] if user.identities else None
    withdrawn = user.status == STATUS_WITHDRAWN and user.withdrawn_at is not None
    return {
        "id": user.id,
        "nickname": user.nickname,
        "email": user.email,
        "login_id": identity.login_id if identity else None,
        "provider": identity.provider if identity else "local",
        "status": user.status,
        "created_at": _aware(user.created_at),
        "withdrawn_at": _aware(user.withdrawn_at),
        "purge_at": _aware(account_service.purge_at(user.withdrawn_at))
        if withdrawn
        else None,
        "last_visit_date": last_visit,
        "completed_exercises": completed,
    }


def list_members(
    db: Session, query: str | None, status: str | None, page: int, size: int
) -> MemberListResponse:
    size = min(max(size, 1), MAX_PAGE_SIZE)
    page = max(page, 1)
    users, total = repo.search_members(
        db, (query or "").strip() or None, status, size, (page - 1) * size
    )
    ids = [u.id for u in users]
    visits = repo.last_visit_dates(db, ids)
    counts = repo.completed_exercise_counts(db, ids)
    return MemberListResponse(
        items=[
            MemberListItem(**_item_fields(u, visits.get(u.id), counts.get(u.id, 0)))
            for u in users
        ],
        total=total,
        page=page,
        size=size,
    )


def _log(db: Session, admin: User, target: User, action: str) -> None:
    repo.add_audit_log(
        db,
        AdminAuditLog(
            admin_id=admin.id,
            admin_nickname=admin.nickname,
            target_user_id=target.id,
            target_nickname=target.nickname,
            action=action,
        ),
    )


def get_member_detail(db: Session, admin: User, user_id: int) -> MemberDetail:
    """회원 상세. 조회했다는 사실을 이력에 남긴다."""
    user = repo.get_member(db, user_id)
    if user is None:
        raise _not_found()
    _log(db, admin, user, ACTION_VIEW_MEMBER)
    db.commit()
    return _detail(db, user)


def _detail(db: Session, user: User) -> MemberDetail:
    visits = repo.last_visit_dates(db, [user.id])
    counts = repo.completed_exercise_counts(db, [user.id])
    records = repo.recent_records(db, user.id, RECENT_RECORDS)
    return MemberDetail(
        **_item_fields(user, visits.get(user.id), counts.get(user.id, 0)),
        onboarding_completed=user.onboarding_completed,
        exercise_level=user.exercise_level,
        due_date=user.due_date,
        visit_days_last_30=repo.visit_day_count(
            db, user.id, today_kst() - timedelta(days=29)
        ),
        recent_records=[
            MemberRecord(
                started_at=_aware(started_at),
                exercise_name=name,
                is_completed=done,
                total_score=float(score) if score is not None else None,
            )
            for started_at, name, done, score in records
        ],
        history=[
            MemberHistory(
                action=log.action,
                admin_nickname=log.admin_nickname,
                created_at=_aware(log.created_at),
            )
            for log in repo.audit_logs_for_member(db, user.id, HISTORY_LIMIT)
        ],
    )


def withdraw_member(
    db: Session,
    admin: User,
    user_id: int,
    kakao_client: KakaoClient | None = None,
) -> MemberDetail:
    """회원을 강제로 탈퇴(유예) 처리한다. 본인이 탈퇴했을 때와 같이 복구할 수 있는 유예 상태가 된다."""
    user = repo.get_member(db, user_id)
    if user is None:
        raise _not_found()
    if user.status != STATUS_ACTIVE:
        raise AppError(409, "MEMBER_ALREADY_WITHDRAWN", "이미 탈퇴 처리된 회원입니다.")
    # 이력은 같은 트랜잭션에 올려 두고, withdraw의 커밋으로 조치와 함께 저장된다.
    _log(db, admin, user, ACTION_WITHDRAW_MEMBER)
    try:
        account_service.withdraw(db, user, kakao_client)
    except Exception:
        db.rollback()
        raise
    db.refresh(user)
    return _detail(db, user)


def restore_member(db: Session, admin: User, user_id: int) -> MemberDetail:
    """탈퇴 유예 중인 회원을 이용 중으로 되돌린다. 유예 기간이 지났으면 복구할 수 없다."""
    user = repo.get_member(db, user_id)
    if user is None:
        raise _not_found()
    now = utc_now()
    if (
        user.status != STATUS_WITHDRAWN
        or user.withdrawn_at is None
        or account_service.purge_at(user.withdrawn_at) <= now
    ):
        raise AppError(
            409, "MEMBER_NOT_RESTORABLE", "복구할 수 있는 탈퇴 유예 회원이 아닙니다."
        )
    user.status = STATUS_ACTIVE
    user.withdrawn_at = None
    _log(db, admin, user, ACTION_RESTORE_MEMBER)
    db.commit()
    db.refresh(user)
    return _detail(db, user)
