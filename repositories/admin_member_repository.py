"""관리자 회원관리용 조회. 대상은 일반 회원(role=user)뿐이다."""

from collections.abc import Sequence
from datetime import date, datetime

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from models.admin_audit_log import AdminAuditLog
from models.auth_identity import AuthIdentity
from models.daily_visit import DailyVisit
from models.exercise import Exercise
from models.exercise_record import ExerciseRecord
from models.user import ROLE_USER, User


def _escape_like(text: str) -> str:
    return text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def search_members(
    db: Session, query: str | None, status: str | None, limit: int, offset: int
) -> tuple[list[User], int]:
    """닉네임·이메일·로그인 아이디로 검색한 일반 회원과 전체 수. 가입 최신 순이다."""
    conditions = [User.role == ROLE_USER]
    if status:
        conditions.append(User.status == status)
    if query:
        pattern = f"%{_escape_like(query)}%"
        has_login_id = (
            select(AuthIdentity.id)
            .where(
                AuthIdentity.user_id == User.id,
                AuthIdentity.login_id.like(pattern, escape="\\"),
            )
            .exists()
        )
        conditions.append(
            or_(
                User.nickname.like(pattern, escape="\\"),
                User.email.like(pattern, escape="\\"),
                has_login_id,
            )
        )
    total = db.scalar(select(func.count()).select_from(User).where(*conditions)) or 0
    users = list(
        db.scalars(
            select(User)
            .where(*conditions)
            .order_by(User.created_at.desc(), User.id.desc())
            .limit(limit)
            .offset(offset)
        )
    )
    return users, total


def get_member(db: Session, user_id: int) -> User | None:
    """일반 회원 한 명. 관리자 계정이거나 없으면 None이다."""
    user = db.get(User, user_id)
    return user if user is not None and user.role == ROLE_USER else None


def last_visit_dates(db: Session, user_ids: Sequence[int]) -> dict[int, date]:
    if not user_ids:
        return {}
    rows = db.execute(
        select(DailyVisit.user_id, func.max(DailyVisit.visit_date))
        .where(DailyVisit.user_id.in_(user_ids))
        .group_by(DailyVisit.user_id)
    )
    return {user_id: last for user_id, last in rows}


def completed_exercise_counts(
    db: Session, user_ids: Sequence[int]
) -> dict[int, int]:
    if not user_ids:
        return {}
    rows = db.execute(
        select(ExerciseRecord.user_id, func.count())
        .where(
            ExerciseRecord.user_id.in_(user_ids),
            ExerciseRecord.is_completed.is_(True),
        )
        .group_by(ExerciseRecord.user_id)
    )
    return {user_id: count for user_id, count in rows}


def recent_records(
    db: Session, user_id: int, limit: int
) -> list[tuple[datetime, str, bool, object]]:
    """최근 운동 기록 (시작 시각, 운동 이름, 완료 여부, 점수)."""
    rows = db.execute(
        select(
            ExerciseRecord.started_at,
            Exercise.exercise_name,
            ExerciseRecord.is_completed,
            ExerciseRecord.total_score,
        )
        .join(Exercise, Exercise.id == ExerciseRecord.exercise_id)
        .where(ExerciseRecord.user_id == user_id)
        .order_by(ExerciseRecord.started_at.desc(), ExerciseRecord.id.desc())
        .limit(limit)
    )
    return [(r[0], r[1], r[2], r[3]) for r in rows]


def visit_day_count(db: Session, user_id: int, since: date) -> int:
    return (
        db.scalar(
            select(func.count())
            .select_from(DailyVisit)
            .where(DailyVisit.user_id == user_id, DailyVisit.visit_date >= since)
        )
        or 0
    )


def add_audit_log(db: Session, log: AdminAuditLog) -> None:
    """이력을 추가한다. 커밋은 호출한 쪽에서 해서, 조치와 이력이 함께 저장되거나 함께 취소되게 한다."""
    db.add(log)


def audit_logs_for_member(
    db: Session, user_id: int, limit: int
) -> list[AdminAuditLog]:
    return list(
        db.scalars(
            select(AdminAuditLog)
            .where(AdminAuditLog.target_user_id == user_id)
            .order_by(AdminAuditLog.created_at.desc(), AdminAuditLog.id.desc())
            .limit(limit)
        )
    )
