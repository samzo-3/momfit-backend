"""관리자 라우터. 모든 라우트는 관리자만 호출할 수 있다."""

from datetime import date

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from api.deps import require_admin
from db.session import get_db
from models.user import User
from schemas.admin import (
    ExerciseStatsResponse,
    Period,
    SummaryResponse,
    UserStatsResponse,
    VisitStatsResponse,
)
from schemas.user import UserResponse
from services.admin import stats_service
from services.user.user_service import to_user_response

router = APIRouter(prefix="/api/admin", tags=["admin"])


@router.get("/me", response_model=UserResponse)
def read_admin_me(admin: User = Depends(require_admin)) -> UserResponse:
    """관리자 본인의 프로필. 프론트가 관리자 화면 진입 가능 여부를 서버 기준으로 확인하는 데 쓴다."""
    return to_user_response(admin)


@router.get("/stats/summary", response_model=SummaryResponse)
def read_summary(
    _: User = Depends(require_admin), db: Session = Depends(get_db)
) -> SummaryResponse:
    """요약 카드: 전체 회원, 오늘 신규 가입, 탈퇴 유예 중, 오늘 완료한 운동 수."""
    return stats_service.summary(db)


@router.get("/stats/exercises", response_model=ExerciseStatsResponse)
def read_exercise_stats(
    period: Period = "day",
    start: date | None = Query(default=None, alias="from", description="시작일(KST, 포함)"),
    end: date | None = Query(default=None, alias="to", description="종료일(KST, 포함)"),
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> ExerciseStatsResponse:
    """운동별 완료 횟수(구간별)와 운동별 합계·평균 점수. 생략하면 최근 30일이다."""
    return stats_service.exercise_stats(db, period, start, end)


@router.get("/stats/users", response_model=UserStatsResponse)
def read_user_stats(
    period: Period = "day",
    start: date | None = Query(default=None, alias="from", description="시작일(KST, 포함)"),
    end: date | None = Query(default=None, alias="to", description="종료일(KST, 포함)"),
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> UserStatsResponse:
    """기간별 신규 가입·탈퇴 요청 수. 생략하면 최근 30일이다."""
    return stats_service.user_stats(db, period, start, end)


@router.get("/stats/visits", response_model=VisitStatsResponse)
def read_visit_stats(
    period: Period = "day",
    start: date | None = Query(default=None, alias="from", description="시작일(KST, 포함)"),
    end: date | None = Query(default=None, alias="to", description="종료일(KST, 포함)"),
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> VisitStatsResponse:
    """구간별 방문자 수(일별=DAU, 주별=WAU, 월별=MAU)와 오늘 기준 DAU·WAU·MAU. 생략하면 최근 30일이다."""
    return stats_service.visit_stats(db, period, start, end)
