"""관리자 통계 API (요약, 운동 횟수, 가입·탈퇴 추이)."""

from datetime import date, datetime, timedelta

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from core.clock import kst_date, kst_day_start_utc, utc_now
from models.exercise import Exercise
from models.exercise_criteria_version import ExerciseCriteriaVersion
from models.daily_visit import DailyVisit
from models.exercise_record import ExerciseRecord
from models.user import ROLE_ADMIN, STATUS_WITHDRAWN, User
from services.admin import stats_service
from tests.helpers import signup_payload

SUMMARY = "/api/admin/stats/summary"
EXERCISES = "/api/admin/stats/exercises"
USERS = "/api/admin/stats/users"
VISITS = "/api/admin/stats/visits"


def _bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _signup(client: TestClient, n: int) -> tuple[str, int]:
    response = client.post(
        "/api/auth/signup",
        json=signup_payload(login_id=f"member{n:02d}", email=f"m{n}@example.com"),
    )
    assert response.status_code == 201
    token = response.json()["access_token"]
    return token, client.get("/api/users/me", headers=_bearer(token)).json()["id"]


def _admin(client: TestClient, db: Session) -> dict[str, str]:
    token, user_id = _signup(client, 99)
    db.get(User, user_id).role = ROLE_ADMIN
    db.commit()
    return _bearer(token)


def _exercise(db: Session, exercise_id: int, name: str) -> None:
    db.add(Exercise(id=exercise_id, exercise_name=name, video_url="https://example.com/v"))
    db.flush()
    db.add(
        ExerciseCriteriaVersion(
            id=exercise_id,
            exercise_id=exercise_id,
            evaluation_criteria={},
            criteria_version="v1",
            schema_version=1,
        )
    )
    db.commit()


def _record(
    db: Session,
    user_id: int,
    started_at_utc: str,
    *,
    exercise_id: int = 1,
    score: float | None = 80,
    completed: bool = True,
) -> None:
    db.add(
        ExerciseRecord(
            id=db.query(ExerciseRecord).count() + 1,
            user_id=user_id,
            exercise_id=exercise_id,
            exercise_criteria_version_id=exercise_id,
            status="completed" if completed else "in_progress",
            is_completed=completed,
            total_score=score,
            started_at=datetime.fromisoformat(started_at_utc),
        )
    )
    db.commit()


def _utc_of_kst(day: date, hour: int = 12) -> str:
    return (kst_day_start_utc(day) + timedelta(hours=hour)).isoformat()


# ---------- 접근 제어 ----------


def test_일반_사용자는_통계_API가_403이다(client: TestClient) -> None:
    token, _ = _signup(client, 1)

    for url in (SUMMARY, EXERCISES, USERS, VISITS):
        assert client.get(url, headers=_bearer(token)).status_code == 403


# ---------- 요약 ----------


def test_요약은_일반_회원만_세고_관리자는_제외한다(
    client: TestClient, db_session: Session
) -> None:
    _exercise(db_session, 1, "Side Kick")
    _, first = _signup(client, 1)
    _, second = _signup(client, 2)
    _, third = _signup(client, 3)
    admin = _admin(client, db_session)
    # 3번 회원은 탈퇴 유예 중
    withdrawn = db_session.get(User, third)
    withdrawn.status = STATUS_WITHDRAWN
    withdrawn.withdrawn_at = utc_now()
    db_session.commit()
    today = kst_date(utc_now())
    _record(db_session, first, _utc_of_kst(today))
    _record(db_session, first, _utc_of_kst(today), completed=False)
    _record(db_session, second, _utc_of_kst(today - timedelta(days=1)))

    body = client.get(SUMMARY, headers=admin).json()

    assert body == {
        "total_users": 2,  # 탈퇴 유예 중인 3번과 관리자는 제외
        "new_users_today": 3,  # 탈퇴 유예 중이어도 오늘 가입한 사실은 센다
        "withdrawn_users": 1,
        "exercises_today": 1,  # 오늘 완료한 것만
        "visitors_today": 3,  # 가입할 때 방문이 기록된 일반 회원 3명(관리자 제외)
    }


# ---------- 운동별 완료 횟수 ----------


def _by_period(body: dict) -> list[tuple[str, dict[int, int]]]:
    """series를 (구간 시작일, {운동 id: 횟수})로 읽는다."""
    return [
        (p["period_start"], {c["exercise_id"]: c["count"] for c in p["counts"]})
        for p in body["series"]
    ]


def _totals(body: dict) -> dict[int, tuple[int, float | None]]:
    return {
        e["exercise_id"]: (e["total_count"], e["average_score"])
        for e in body["exercises"]
    }


def test_일별_운동별_횟수는_기록이_없는_날도_0으로_채운다(
    client: TestClient, db_session: Session
) -> None:
    _exercise(db_session, 1, "Side Kick")
    _exercise(db_session, 2, "Squat")
    _, user = _signup(client, 1)
    admin = _admin(client, db_session)
    _record(db_session, user, "2026-03-01T01:00:00", exercise_id=1)
    _record(db_session, user, "2026-03-01T02:00:00", exercise_id=2)
    _record(db_session, user, "2026-03-01T03:00:00", exercise_id=2)
    _record(db_session, user, "2026-03-03T01:00:00", exercise_id=1)

    body = client.get(
        EXERCISES, params={"from": "2026-03-01", "to": "2026-03-04"}, headers=admin
    ).json()

    assert _by_period(body) == [
        ("2026-03-01", {1: 1, 2: 2}),
        ("2026-03-02", {1: 0, 2: 0}),  # 모든 운동이 0으로 들어 있다
        ("2026-03-03", {1: 1, 2: 0}),
        ("2026-03-04", {1: 0, 2: 0}),
    ]


def test_운동별_합계와_평균_점수는_선택한_기간만_센다(
    client: TestClient, db_session: Session
) -> None:
    _exercise(db_session, 1, "Side Kick")
    _exercise(db_session, 2, "Squat")
    _, user = _signup(client, 1)
    admin = _admin(client, db_session)
    _record(db_session, user, "2026-03-01T01:00:00", exercise_id=1, score=70)
    _record(db_session, user, "2026-03-01T02:00:00", exercise_id=1, score=90)
    _record(db_session, user, "2026-03-01T03:00:00", exercise_id=1, score=None)
    _record(db_session, user, "2026-03-01T04:00:00", exercise_id=2, score=60)
    _record(db_session, user, "2026-02-01T01:00:00", exercise_id=2, score=10)  # 기간 밖

    body = client.get(
        EXERCISES, params={"from": "2026-03-01", "to": "2026-03-02"}, headers=admin
    ).json()

    assert _totals(body) == {
        1: (3, 80.0),  # 점수가 없는 기록은 평균에서 뺀다
        2: (1, 60.0),
    }


def test_운동은_id_순이고_기록이_없는_운동도_목록에_있다(
    client: TestClient, db_session: Session
) -> None:
    _exercise(db_session, 2, "Squat")
    _exercise(db_session, 1, "Side Kick")
    _exercise(db_session, 3, "Stretch")
    _, user = _signup(client, 1)
    admin = _admin(client, db_session)
    _record(db_session, user, "2026-03-01T01:00:00", exercise_id=2)

    body = client.get(
        EXERCISES, params={"from": "2026-03-01", "to": "2026-03-01"}, headers=admin
    ).json()

    assert [e["exercise_id"] for e in body["exercises"]] == [1, 2, 3]
    assert [e["exercise_name"] for e in body["exercises"]] == [
        "Side Kick",
        "Squat",
        "Stretch",
    ]
    assert _totals(body)[3] == (0, None)


def test_날짜는_한국_시간_기준으로_나눈다(client: TestClient, db_session: Session) -> None:
    _exercise(db_session, 1, "Side Kick")
    _, user = _signup(client, 1)
    admin = _admin(client, db_session)
    _record(db_session, user, "2026-03-01T14:59:59")  # KST 3/1 23:59
    _record(db_session, user, "2026-03-01T15:00:00")  # KST 3/2 00:00

    body = client.get(
        EXERCISES, params={"from": "2026-03-01", "to": "2026-03-02"}, headers=admin
    ).json()

    assert [counts[1] for _, counts in _by_period(body)] == [1, 1]


def test_완료하지_않은_운동은_세지_않는다(client: TestClient, db_session: Session) -> None:
    _exercise(db_session, 1, "Side Kick")
    _, user = _signup(client, 1)
    admin = _admin(client, db_session)
    _record(db_session, user, "2026-03-01T01:00:00", completed=False)

    body = client.get(
        EXERCISES, params={"from": "2026-03-01", "to": "2026-03-01"}, headers=admin
    ).json()

    assert _totals(body) == {1: (0, None)}
    assert _by_period(body) == [("2026-03-01", {1: 0})]


def test_주별은_월요일_시작이고_월별은_1일_시작이다(
    client: TestClient, db_session: Session
) -> None:
    _exercise(db_session, 1, "Side Kick")
    _, user = _signup(client, 1)
    admin = _admin(client, db_session)
    # 2026-03-01은 일요일, 03-02는 월요일
    _record(db_session, user, _utc_of_kst(date(2026, 3, 1)))
    _record(db_session, user, _utc_of_kst(date(2026, 3, 2)))
    _record(db_session, user, _utc_of_kst(date(2026, 3, 8)))
    _record(db_session, user, _utc_of_kst(date(2026, 4, 1)))
    params = {"from": "2026-03-01", "to": "2026-04-05"}

    weeks = client.get(EXERCISES, params={**params, "period": "week"}, headers=admin).json()
    months = client.get(EXERCISES, params={**params, "period": "month"}, headers=admin).json()

    week_counts = {start: counts[1] for start, counts in _by_period(weeks)}
    assert week_counts["2026-02-23"] == 1  # 3/1(일)은 앞선 주
    assert week_counts["2026-03-02"] == 2  # 3/2(월)와 3/8(일)
    assert week_counts["2026-03-30"] == 1  # 4/1(수)
    assert [(start, counts[1]) for start, counts in _by_period(months)] == [
        ("2026-03-01", 3),
        ("2026-04-01", 1),
    ]


def test_기간을_생략하면_오늘까지_최근_30일이다(
    client: TestClient, db_session: Session
) -> None:
    admin = _admin(client, db_session)

    body = client.get(EXERCISES, headers=admin).json()

    assert len(body["series"]) == 30
    assert body["end"] == kst_date(utc_now()).isoformat()
    assert body["period"] == "day"


def test_잘못된_기간은_422다(client: TestClient, db_session: Session) -> None:
    admin = _admin(client, db_session)

    reversed_range = client.get(
        EXERCISES, params={"from": "2026-03-02", "to": "2026-03-01"}, headers=admin
    )
    too_long = client.get(
        USERS, params={"from": "2020-01-01", "to": "2026-03-01"}, headers=admin
    )
    bad_period = client.get(EXERCISES, params={"period": "year"}, headers=admin)

    assert reversed_range.status_code == 422
    assert reversed_range.json()["error"]["code"] == "INVALID_DATE_RANGE"
    assert too_long.status_code == 422
    assert too_long.json()["error"]["code"] == "DATE_RANGE_TOO_LONG"
    assert bad_period.status_code == 422


def test_응답에_개인_정보가_없다(client: TestClient, db_session: Session) -> None:
    _exercise(db_session, 1, "Side Kick")
    _, user = _signup(client, 1)
    admin = _admin(client, db_session)
    _record(db_session, user, "2026-03-01T01:00:00")

    text = client.get(
        EXERCISES, params={"from": "2026-03-01", "to": "2026-03-01"}, headers=admin
    ).text

    assert "m1@example.com" not in text
    assert "member01" not in text
    assert "user_id" not in text


# ---------- 가입·탈퇴 추이 ----------


def test_가입과_탈퇴_추이를_일별로_센다(client: TestClient, db_session: Session) -> None:
    ids = [_signup(client, n)[1] for n in (1, 2, 3)]
    admin = _admin(client, db_session)
    db_session.get(User, ids[0]).created_at = datetime(2026, 3, 1, 1)
    db_session.get(User, ids[1]).created_at = datetime(2026, 3, 1, 5)
    db_session.get(User, ids[2]).created_at = datetime(2026, 3, 3, 1)
    leaving = db_session.get(User, ids[1])
    leaving.status = STATUS_WITHDRAWN
    leaving.withdrawn_at = datetime(2026, 3, 2, 1)
    db_session.commit()

    body = client.get(
        USERS, params={"from": "2026-03-01", "to": "2026-03-03"}, headers=admin
    ).json()

    assert [(p["period_start"], p["signups"], p["withdrawals"]) for p in body["series"]] == [
        ("2026-03-01", 2, 0),
        ("2026-03-02", 0, 1),
        ("2026-03-03", 1, 0),
    ]
    assert body["total_signups"] == 3
    assert body["total_withdrawals"] == 1


def test_관리자_계정은_가입_추이에_세지_않는다(client: TestClient, db_session: Session) -> None:
    admin = _admin(client, db_session)
    today = kst_date(utc_now()).isoformat()

    body = client.get(USERS, params={"from": today, "to": today}, headers=admin).json()

    assert body["total_signups"] == 0


# ---------- 구간 계산 ----------


def test_buckets는_마지막_달까지_빠짐없이_만든다() -> None:
    assert stats_service.buckets(date(2026, 1, 31), date(2026, 3, 1), "month") == [
        date(2026, 1, 1),
        date(2026, 2, 1),
        date(2026, 3, 1),
    ]
    assert stats_service.buckets(date(2026, 12, 15), date(2027, 1, 2), "month") == [
        date(2026, 12, 1),
        date(2027, 1, 1),
    ]


# ---------- 첫 구간 보정 ----------


def test_주별_첫_구간은_기간_앞쪽_날짜도_포함해_센다(
    client: TestClient, db_session: Session
) -> None:
    _exercise(db_session, 1, "Side Kick")
    _, user = _signup(client, 1)
    admin = _admin(client, db_session)
    # 2026-03-04(수)부터 조회하면 첫 주(3/2 월요일 시작)는 기간 밖인 3/2, 3/3도 포함한다.
    _record(db_session, user, _utc_of_kst(date(2026, 3, 2)))
    _record(db_session, user, _utc_of_kst(date(2026, 3, 5)))

    body = client.get(
        EXERCISES,
        params={"from": "2026-03-04", "to": "2026-03-10", "period": "week"},
        headers=admin,
    ).json()

    assert _by_period(body)[0] == ("2026-03-02", {1: 2})
    # 운동별 합계는 선택한 기간(3/4~)만 센다.
    assert _totals(body) == {1: (1, 80.0)}


def test_가입_추이도_첫_구간은_전체를_세고_합계는_기간만_센다(
    client: TestClient, db_session: Session
) -> None:
    ids = [_signup(client, n)[1] for n in (1, 2)]
    admin = _admin(client, db_session)
    db_session.get(User, ids[0]).created_at = datetime(2026, 3, 2, 1)  # 기간 밖(월)
    db_session.get(User, ids[1]).created_at = datetime(2026, 3, 5, 1)
    db_session.commit()

    body = client.get(
        USERS,
        params={"from": "2026-03-04", "to": "2026-03-10", "period": "week"},
        headers=admin,
    ).json()

    assert body["series"][0]["signups"] == 2
    assert body["total_signups"] == 1


# ---------- 방문자 ----------


def _visit(db: Session, user_id: int, day: date) -> None:
    db.add(DailyVisit(visit_date=day, user_id=user_id))
    db.commit()


def _clear_visits(db: Session) -> None:
    db.query(DailyVisit).delete()
    db.commit()


def test_일별_방문자는_하루에_한_번이라도_온_회원_수다(
    client: TestClient, db_session: Session
) -> None:
    _, first = _signup(client, 1)
    _, second = _signup(client, 2)
    admin = _admin(client, db_session)
    _clear_visits(db_session)
    _visit(db_session, first, date(2026, 3, 1))
    _visit(db_session, second, date(2026, 3, 1))
    _visit(db_session, first, date(2026, 3, 3))

    body = client.get(
        VISITS, params={"from": "2026-03-01", "to": "2026-03-04"}, headers=admin
    ).json()

    assert [(p["period_start"], p["visitors"]) for p in body["series"]] == [
        ("2026-03-01", 2),
        ("2026-03-02", 0),
        ("2026-03-03", 1),
        ("2026-03-04", 0),
    ]
    assert body["unique_visitors"] == 2  # 기간 전체에서 중복 없이


def test_주별_방문자는_같은_회원을_한_번만_센다(
    client: TestClient, db_session: Session
) -> None:
    _, first = _signup(client, 1)
    _, second = _signup(client, 2)
    admin = _admin(client, db_session)
    _clear_visits(db_session)
    for day in (date(2026, 3, 2), date(2026, 3, 4), date(2026, 3, 6)):
        _visit(db_session, first, day)  # 같은 주에 3번 방문
    _visit(db_session, second, date(2026, 3, 5))
    _visit(db_session, first, date(2026, 3, 10))  # 다음 주

    body = client.get(
        VISITS,
        params={"from": "2026-03-02", "to": "2026-03-15", "period": "week"},
        headers=admin,
    ).json()

    assert [(p["period_start"], p["visitors"]) for p in body["series"]] == [
        ("2026-03-02", 2),
        ("2026-03-09", 1),
    ]
    assert body["unique_visitors"] == 2


def test_방문자_첫_구간은_기간_앞쪽_방문도_포함한다(
    client: TestClient, db_session: Session
) -> None:
    _, first = _signup(client, 1)
    _, second = _signup(client, 2)
    admin = _admin(client, db_session)
    _clear_visits(db_session)
    _visit(db_session, first, date(2026, 3, 2))  # 기간 밖, 같은 주
    _visit(db_session, second, date(2026, 3, 5))

    body = client.get(
        VISITS,
        params={"from": "2026-03-04", "to": "2026-03-10", "period": "week"},
        headers=admin,
    ).json()

    assert body["series"][0]["visitors"] == 2
    assert body["unique_visitors"] == 1  # 기간 안에서는 second뿐


def test_관리자의_방문은_세지_않는다(client: TestClient, db_session: Session) -> None:
    admin = _admin(client, db_session)  # 가입할 때 오늘 방문이 기록된다
    today = kst_date(utc_now()).isoformat()

    body = client.get(VISITS, params={"from": today, "to": today}, headers=admin).json()

    assert body["series"][-1]["visitors"] == 0
    assert body["current"] == {"dau": 0, "wau": 0, "mau": 0}
    assert client.get(SUMMARY, headers=admin).json()["visitors_today"] == 0


def test_오늘_기준_DAU_WAU_MAU는_기간과_상관없다(
    client: TestClient, db_session: Session
) -> None:
    ids = [_signup(client, n)[1] for n in (1, 2, 3, 4)]
    admin = _admin(client, db_session)
    _clear_visits(db_session)
    today = kst_date(utc_now())
    _visit(db_session, ids[0], today)
    _visit(db_session, ids[1], today - timedelta(days=6))  # 7일 안
    _visit(db_session, ids[2], today - timedelta(days=29))  # 30일 안
    _visit(db_session, ids[3], today - timedelta(days=30))  # 30일 밖
    _visit(db_session, ids[0], today - timedelta(days=3))  # 중복은 한 번만

    body = client.get(
        VISITS, params={"from": "2020-01-01", "to": "2020-01-07"}, headers=admin
    ).json()

    assert body["current"] == {"dau": 1, "wau": 2, "mau": 3}
    assert body["unique_visitors"] == 0  # 조회 기간(2020년)에는 방문이 없다


def test_방문자_기간_오류는_422다(client: TestClient, db_session: Session) -> None:
    admin = _admin(client, db_session)

    response = client.get(
        VISITS, params={"from": "2026-03-02", "to": "2026-03-01"}, headers=admin
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "INVALID_DATE_RANGE"
