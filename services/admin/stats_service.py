"""관리자 대시보드 통계. 날짜는 모두 KST 기준으로 묶는다."""

from collections import Counter, defaultdict
from datetime import date, datetime, timedelta

from sqlalchemy.orm import Session

from core.clock import kst_date, kst_day_start_utc, today_kst
from core.errors import AppError
from repositories import admin_stats_repository as repo
from schemas.admin import (
    ExerciseCount,
    ExerciseInfo,
    ExercisePoint,
    ExerciseStatsResponse,
    Period,
    SummaryResponse,
    UserPoint,
    UserStatsResponse,
    VisitCurrent,
    VisitPoint,
    VisitStatsResponse,
)

DEFAULT_DAYS = 30
MAX_DAYS = 731


def bucket_start(day: date, period: Period) -> date:
    """day가 속한 구간의 시작일. 주는 월요일, 달은 1일."""
    if period == "week":
        return day - timedelta(days=day.weekday())
    if period == "month":
        return day.replace(day=1)
    return day


def _next_bucket(start: date, period: Period) -> date:
    if period == "week":
        return start + timedelta(days=7)
    if period == "month":
        return (start.replace(day=28) + timedelta(days=4)).replace(day=1)
    return start + timedelta(days=1)


def buckets(start: date, end: date, period: Period) -> list[date]:
    """start~end를 덮는 모든 구간의 시작일. 기록이 없는 구간도 0으로 보이도록 빠짐없이 만든다."""
    result = []
    current = bucket_start(start, period)
    while current <= end:
        result.append(current)
        current = _next_bucket(current, period)
    return result


def resolve_range(start: date | None, end: date | None) -> tuple[date, date]:
    """조회 기간을 정한다. 생략하면 오늘까지 최근 30일이다."""
    end = end or today_kst()
    start = start or end - timedelta(days=DEFAULT_DAYS - 1)
    if end < start:
        raise AppError(422, "INVALID_DATE_RANGE", "시작일이 종료일보다 늦습니다.")
    if (end - start).days + 1 > MAX_DAYS:
        raise AppError(
            422, "DATE_RANGE_TOO_LONG", f"한 번에 {MAX_DAYS}일까지만 조회할 수 있습니다."
        )
    return start, end


def _bounds(start: date, end: date) -> tuple[datetime, datetime]:
    return kst_day_start_utc(start), kst_day_start_utc(end + timedelta(days=1))


def _series_bounds(
    start: date, end: date, period: Period
) -> tuple[datetime, datetime]:
    """차트용 조회 범위. 주·월 단위의 첫 구간이 기간 중간에서 시작해도 그 구간 전체를 읽어 낮게 보이지 않게 한다."""
    return _bounds(buckets(start, end, period)[0], end)


def summary(db: Session, today: date | None = None) -> SummaryResponse:
    today = today or today_kst()
    day_start, day_end = _bounds(today, today)
    return SummaryResponse(
        total_users=repo.count_active_members(db),
        new_users_today=len(repo.signup_times(db, day_start, day_end)),
        withdrawn_users=repo.count_withdrawn_members(db),
        exercises_today=len(repo.completed_exercises(db, day_start, day_end)),
        visitors_today=repo.count_visitors(db, today, today),
    )


def exercise_stats(
    db: Session, period: Period, start: date | None, end: date | None
) -> ExerciseStatsResponse:
    """운동별 완료 횟수. 구간별 추이는 첫 구간 전체를, 운동별 합계·평균 점수는 선택한 기간만 센다."""
    start, end = resolve_range(start, end)
    all_rows = repo.completed_exercises(db, *_series_bounds(start, end, period))
    exercises = repo.all_exercises(db)

    counts: dict[date, Counter[int]] = defaultdict(Counter)
    totals: Counter[int] = Counter()
    scores: dict[int, list[float]] = defaultdict(list)
    for started_at, score, exercise_id, _name in all_rows:
        day = kst_date(started_at)
        counts[bucket_start(day, period)][exercise_id] += 1
        if day >= start:
            totals[exercise_id] += 1
            if score is not None:
                scores[exercise_id].append(float(score))

    return ExerciseStatsResponse(
        period=period,
        start=start,
        end=end,
        exercises=[
            ExerciseInfo(
                exercise_id=eid,
                exercise_name=name,
                total_count=totals[eid],
                average_score=_average(scores[eid]),
            )
            for eid, name in exercises
        ],
        series=[
            ExercisePoint(
                period_start=b,
                counts=[
                    ExerciseCount(exercise_id=eid, count=counts[b][eid])
                    for eid, _name in exercises
                ],
            )
            for b in buckets(start, end, period)
        ],
    )


def user_stats(
    db: Session, period: Period, start: date | None, end: date | None
) -> UserStatsResponse:
    start, end = resolve_range(start, end)
    bounds = _series_bounds(start, end, period)
    signup_days = [kst_date(t) for t in repo.signup_times(db, *bounds)]
    withdrawal_days = [kst_date(t) for t in repo.withdrawal_times(db, *bounds)]
    signups = Counter(bucket_start(d, period) for d in signup_days)
    withdrawals = Counter(bucket_start(d, period) for d in withdrawal_days)
    return UserStatsResponse(
        period=period,
        start=start,
        end=end,
        total_signups=sum(1 for d in signup_days if d >= start),
        total_withdrawals=sum(1 for d in withdrawal_days if d >= start),
        series=[
            UserPoint(period_start=b, signups=signups[b], withdrawals=withdrawals[b])
            for b in buckets(start, end, period)
        ],
    )


def visit_stats(
    db: Session,
    period: Period,
    start: date | None,
    end: date | None,
    today: date | None = None,
) -> VisitStatsResponse:
    """구간별 방문자 수(그 구간에 한 번이라도 방문한 회원, 중복 제외)와 오늘 기준 DAU·WAU·MAU."""
    start, end = resolve_range(start, end)
    today = today or today_kst()
    pairs = repo.visit_pairs(db, buckets(start, end, period)[0], end)

    visitors: dict[date, set[int]] = defaultdict(set)
    in_range: set[int] = set()
    for day, user_id in pairs:
        visitors[bucket_start(day, period)].add(user_id)
        if day >= start:
            in_range.add(user_id)

    return VisitStatsResponse(
        period=period,
        start=start,
        end=end,
        unique_visitors=len(in_range),
        current=VisitCurrent(
            dau=repo.count_visitors(db, today, today),
            wau=repo.count_visitors(db, today - timedelta(days=6), today),
            mau=repo.count_visitors(db, today - timedelta(days=29), today),
        ),
        series=[
            VisitPoint(period_start=b, visitors=len(visitors[b]))
            for b in buckets(start, end, period)
        ],
    )


def _average(values: list[float]) -> float | None:
    return round(sum(values) / len(values), 1) if values else None
