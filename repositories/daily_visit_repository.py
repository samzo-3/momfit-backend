"""daily_visits 테이블 접근."""

from datetime import date

from sqlalchemy import delete
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from models.daily_visit import DailyVisit


def record(db: Session, user_id: int, visit_date: date) -> None:
    """그날의 방문을 기록한다. 이미 있으면 아무것도 하지 않는다. (커밋은 호출한 쪽에서 한다)"""
    if db.get(DailyVisit, (visit_date, user_id)) is not None:
        return
    try:
        # 같은 사용자의 요청이 동시에 들어와 먼저 저장된 경우, 바깥 트랜잭션은 건드리지 않고 무시한다.
        with db.begin_nested():
            db.add(DailyVisit(visit_date=visit_date, user_id=user_id))
    except IntegrityError:
        pass


def delete_all_for_user(db: Session, user_id: int) -> None:
    """사용자의 방문 기록을 모두 삭제한다."""
    db.execute(delete(DailyVisit).where(DailyVisit.user_id == user_id))
