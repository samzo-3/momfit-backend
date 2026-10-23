"""관리자 라우터. 모든 라우트는 관리자만 호출할 수 있다."""

from datetime import date

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from api.deps import require_admin
from db.session import get_db
from models.user import User
from schemas.admin import (
    ExerciseStatsResponse,
    MemberDetail,
    MemberListResponse,
    MemberStatus,
    Period,
    SummaryResponse,
    UserStatsResponse,
    VisitStatsResponse,
)
from schemas.user import UserResponse
from services.admin import member_service, stats_service
from services.auth.kakao_client import KakaoClient, get_kakao_client
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


@router.get("/members", response_model=MemberListResponse)
def list_members(
    q: str | None = Query(default=None, max_length=100, description="닉네임·이메일·아이디 검색"),
    status: MemberStatus | None = None,
    page: int = Query(default=1, ge=1),
    size: int = Query(default=20, ge=1, le=member_service.MAX_PAGE_SIZE),
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> MemberListResponse:
    """일반 회원 목록. 가입 최신 순이다."""
    return member_service.list_members(db, q, status, page, size)


@router.get("/members/{user_id}", response_model=MemberDetail)
def read_member(
    user_id: int,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> MemberDetail:
    """회원 상세. 조회할 때마다 이력이 남는다."""
    return member_service.get_member_detail(db, admin, user_id)


@router.post("/members/{user_id}/withdraw", response_model=MemberDetail)
def withdraw_member(
    user_id: int,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
    kakao_client: KakaoClient = Depends(get_kakao_client),
) -> MemberDetail:
    """회원을 강제 탈퇴(유예) 처리한다. 유예 기간 안에는 복구할 수 있다."""
    return member_service.withdraw_member(db, admin, user_id, kakao_client)


@router.post("/members/{user_id}/restore", response_model=MemberDetail)
def restore_member(
    user_id: int,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> MemberDetail:
    """탈퇴 유예 중인 회원을 복구한다."""
    return member_service.restore_member(db, admin, user_id)
