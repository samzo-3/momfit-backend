"""관리자 통계 응답 스키마. 개인 정보 없이 집계값만 담는다."""

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel

Period = Literal["day", "week", "month"]


class SummaryResponse(BaseModel):
    """GET /admin/stats/summary 응답. 일반 회원 기준이며 관리자 계정은 세지 않는다."""

    total_users: int
    new_users_today: int
    withdrawn_users: int
    exercises_today: int
    visitors_today: int


class ExerciseInfo(BaseModel):
    """운동 한 종류의 선택 기간 합계. 운동이 아직 한 번도 없어도 목록에 포함해 색·순서가 고정되게 한다."""

    exercise_id: int
    exercise_name: str
    total_count: int
    average_score: float | None


class ExerciseCount(BaseModel):
    exercise_id: int
    count: int


class ExercisePoint(BaseModel):
    """한 구간의 운동별 완료 횟수. counts에는 모든 운동이 (0 포함) 들어 있다."""

    period_start: date
    counts: list[ExerciseCount]


class ExerciseStatsResponse(BaseModel):
    """GET /admin/stats/exercises 응답. 운동별로 완료한 횟수만 센다. 운동은 id 순이다."""

    period: Period
    start: date
    end: date
    exercises: list[ExerciseInfo]
    series: list[ExercisePoint]


class UserPoint(BaseModel):
    period_start: date
    signups: int
    withdrawals: int


class UserStatsResponse(BaseModel):
    """GET /admin/stats/users 응답. 탈퇴는 현재 탈퇴 유예 중인 계정의 요청일 기준이다."""

    period: Period
    start: date
    end: date
    total_signups: int
    total_withdrawals: int
    series: list[UserPoint]


MemberStatus = Literal["active", "withdrawn"]


class MemberListItem(BaseModel):
    """회원 목록의 한 행."""

    id: int
    nickname: str
    email: str | None
    login_id: str | None
    provider: Literal["local", "kakao"]
    status: MemberStatus
    created_at: datetime
    withdrawn_at: datetime | None
    purge_at: datetime | None
    last_visit_date: date | None
    completed_exercises: int


class MemberListResponse(BaseModel):
    items: list[MemberListItem]
    total: int
    page: int
    size: int


class MemberRecord(BaseModel):
    started_at: datetime
    exercise_name: str
    is_completed: bool
    total_score: float | None


class MemberHistory(BaseModel):
    """회원에 대한 관리자 조회·조치 이력의 한 줄."""

    action: Literal["view_member", "withdraw_member", "restore_member"]
    admin_nickname: str
    created_at: datetime


class MemberDetail(MemberListItem):
    """회원 상세. 온보딩·건강 관련 값은 관리자가 조회할 때마다 이력이 남는다."""

    onboarding_completed: bool
    exercise_level: Literal["low", "medium", "high"] | None
    due_date: date | None
    visit_days_last_30: int
    recent_records: list[MemberRecord]
    history: list[MemberHistory]


class VisitPoint(BaseModel):
    period_start: date
    visitors: int


class VisitCurrent(BaseModel):
    """오늘 기준 방문자 수. 조회 기간과 상관없이 고정이다."""

    dau: int  # 오늘
    wau: int  # 오늘을 포함한 최근 7일
    mau: int  # 오늘을 포함한 최근 30일


class VisitStatsResponse(BaseModel):
    """GET /admin/stats/visits 응답. 로그인한 일반 회원이 그 구간에 한 번이라도 방문했는지를 센다."""

    period: Period
    start: date
    end: date
    unique_visitors: int
    current: VisitCurrent
    series: list[VisitPoint]
