"""관리자 통계용 조회. 집계는 서비스에서 하고, 여기서는 필요한 열만 가져온다."""

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from models.daily_visit import DailyVisit
from models.exercise import Exercise
from models.exercise_record import ExerciseRecord
from models.user import ROLE_USER, STATUS_ACTIVE, STATUS_WITHDRAWN, User


def count_members(db: Session, status: str | None = None) -> int:
    """일반 회원 수. status를 주면 그 상태만 센다."""
    query = select(func.count()).select_from(User).where(User.role == ROLE_USER)
    if status is not None:
        query = query.where(User.status == status)
    return db.scalar(query) or 0


def count_active_members(db: Session) -> int:
    return count_members(db, STATUS_ACTIVE)


def count_withdrawn_members(db: Session) -> int:
    return count_members(db, STATUS_WITHDRAWN)


def signup_times(db: Session, start: datetime, end: datetime) -> list[datetime]:
    """[start, end) 사이에 가입한 일반 회원의 가입 시각(naive UTC)."""
    return list(
        db.scalars(
            select(User.created_at).where(
                User.role == ROLE_USER,
                User.created_at >= start,
                User.created_at < end,
            )
        )
    )


def withdrawal_times(db: Session, start: datetime, end: datetime) -> list[datetime]:
    """[start, end) 사이에 탈퇴를 요청한 일반 회원의 요청 시각. 현재 탈퇴 유예 중인 계정만 남아 있다."""
    return list(
        db.scalars(
            select(User.withdrawn_at).where(
                User.role == ROLE_USER,
                User.status == STATUS_WITHDRAWN,
                User.withdrawn_at >= start,
                User.withdrawn_at < end,
            )
        )
    )


def completed_exercises(
    db: Session, start: datetime, end: datetime
) -> list[tuple[datetime, Decimal | None, int, str]]:
    """[start, end) 사이에 시작해 완료한 운동의 (시작 시각, 점수, 운동 id, 운동 이름)."""
    rows = db.execute(
        select(
            ExerciseRecord.started_at,
            ExerciseRecord.total_score,
            ExerciseRecord.exercise_id,
            Exercise.exercise_name,
        )
        .join(Exercise, Exercise.id == ExerciseRecord.exercise_id)
        .where(
            ExerciseRecord.is_completed.is_(True),
            ExerciseRecord.started_at >= start,
            ExerciseRecord.started_at < end,
        )
    )
    return [(r[0], r[1], r[2], r[3]) for r in rows]


def visit_pairs(db: Session, start: date, end: date) -> list[tuple[date, int]]:
    """start~end(양 끝 포함)에 방문한 일반 회원의 (방문 날짜, 회원 id)."""
    rows = db.execute(
        select(DailyVisit.visit_date, DailyVisit.user_id)
        .join(User, User.id == DailyVisit.user_id)
        .where(
            User.role == ROLE_USER,
            DailyVisit.visit_date >= start,
            DailyVisit.visit_date <= end,
        )
    )
    return [(r[0], r[1]) for r in rows]


def count_visitors(db: Session, start: date, end: date) -> int:
    """start~end(양 끝 포함)에 한 번이라도 방문한 일반 회원 수."""
    return (
        db.scalar(
            select(func.count(func.distinct(DailyVisit.user_id)))
            .join(User, User.id == DailyVisit.user_id)
            .where(
                User.role == ROLE_USER,
                DailyVisit.visit_date >= start,
                DailyVisit.visit_date <= end,
            )
        )
        or 0
    )


def all_exercises(db: Session) -> list[tuple[int, str]]:
    """등록된 모든 운동의 (id, 이름). id 순."""
    return [(r[0], r[1]) for r in db.execute(select(Exercise.id, Exercise.exercise_name).order_by(Exercise.id))]
