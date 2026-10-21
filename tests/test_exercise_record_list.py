"""GET /api/exercise-records (캘린더용 기간 조회) 테스트."""

from datetime import datetime

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from models.exercise import Exercise
from models.exercise_criteria_version import ExerciseCriteriaVersion
from models.exercise_record import ExerciseRecord
from tests.helpers import signup_payload


def _signup(client: TestClient, **overrides) -> tuple[str, int]:
    response = client.post("/api/auth/signup", json=signup_payload(**overrides))
    assert response.status_code == 201
    token = response.json()["access_token"]
    me = client.get("/api/users/me", headers={"Authorization": f"Bearer {token}"})
    return token, me.json()["id"]


def _bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _criteria_id(db: Session) -> int:
    exercise = db.query(Exercise).first()
    if exercise is None:
        exercise = Exercise(id=1, exercise_name="Side Kick", video_url="https://example.com/v")
        db.add(exercise)
        db.flush()
        db.add(
            ExerciseCriteriaVersion(
                id=1,
                exercise_id=exercise.id,
                evaluation_criteria={},
                criteria_version="v1",
                schema_version=1,
            )
        )
        db.flush()
    return db.query(ExerciseCriteriaVersion).first().id


def _add_record(
    db: Session,
    user_id: int,
    started_at_utc: str,
    *,
    completed: bool = True,
) -> ExerciseRecord:
    criteria_id = _criteria_id(db)
    # SQLite는 BigInteger 기본키를 자동 증가시키지 않으므로 id를 직접 지정한다.
    record = ExerciseRecord(
        id=(db.query(ExerciseRecord).count() + 1),
        user_id=user_id,
        exercise_id=db.query(Exercise).first().id,
        exercise_criteria_version_id=criteria_id,
        status="completed" if completed else "in_progress",
        is_completed=completed,
        started_at=datetime.fromisoformat(started_at_utc),
    )
    db.add(record)
    db.commit()
    return record


def _list(client: TestClient, token: str, start: str, end: str):
    return client.get(
        "/api/exercise-records",
        params={"from": start, "to": end},
        headers=_bearer(token),
    )


def test_기간_안의_내_기록을_KST_날짜와_함께_돌려준다(
    client: TestClient, db_session: Session
) -> None:
    token, user_id = _signup(client)
    _add_record(db_session, user_id, "2026-10-19 01:00:00")  # KST 10/19 10:00
    _add_record(db_session, user_id, "2026-10-05 03:30:00", completed=False)

    response = _list(client, token, "2026-10-01", "2026-10-31")

    assert response.status_code == 200
    items = response.json()["items"]
    assert [(i["date"], i["is_completed"]) for i in items] == [
        ("2026-10-05", False),
        ("2026-10-19", True),
    ]
    assert items[0]["status"] == "in_progress"


def test_UTC로는_전날이어도_KST_날짜로_분류한다(
    client: TestClient, db_session: Session
) -> None:
    token, user_id = _signup(client)
    # UTC 10/18 16:00 = KST 10/19 01:00
    _add_record(db_session, user_id, "2026-10-18 16:00:00")

    items = _list(client, token, "2026-10-19", "2026-10-19").json()["items"]

    assert [i["date"] for i in items] == ["2026-10-19"]
    assert _list(client, token, "2026-10-18", "2026-10-18").json()["items"] == []


def test_기간_경계는_KST_하루_단위로_포함한다(
    client: TestClient, db_session: Session
) -> None:
    token, user_id = _signup(client)
    _add_record(db_session, user_id, "2026-09-30 14:59:59")  # KST 9/30 23:59:59
    _add_record(db_session, user_id, "2026-09-30 15:00:00")  # KST 10/1 00:00:00
    _add_record(db_session, user_id, "2026-10-31 14:59:59")  # KST 10/31 23:59:59
    _add_record(db_session, user_id, "2026-10-31 15:00:00")  # KST 11/1 00:00:00

    items = _list(client, token, "2026-10-01", "2026-10-31").json()["items"]

    assert [i["date"] for i in items] == ["2026-10-01", "2026-10-31"]


def test_다른_사용자의_기록은_보이지_않는다(
    client: TestClient, db_session: Session
) -> None:
    token, _ = _signup(client)
    _, other_id = _signup(
        client,
        login_id="momfit02",
        email="other@example.com",
        nickname="다른맘",
    )
    _add_record(db_session, other_id, "2026-10-19 01:00:00")

    assert _list(client, token, "2026-10-01", "2026-10-31").json() == {"items": []}


def test_시작일이_종료일보다_늦으면_422이다(client: TestClient) -> None:
    token, _ = _signup(client)

    response = _list(client, token, "2026-10-31", "2026-10-01")

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "INVALID_DATE_RANGE"


def test_조회_기간은_62일까지다(client: TestClient) -> None:
    token, _ = _signup(client)

    assert _list(client, token, "2026-10-01", "2026-11-30").status_code == 200  # 61일
    assert _list(client, token, "2026-10-01", "2026-12-01").status_code == 200  # 62일
    too_long = _list(client, token, "2026-10-01", "2026-12-02")  # 63일

    assert too_long.status_code == 422
    assert too_long.json()["error"]["code"] == "DATE_RANGE_TOO_LONG"


def test_날짜_형식이_틀리거나_빠지면_422이다(client: TestClient) -> None:
    token, _ = _signup(client)

    assert _list(client, token, "2026/10/01", "2026-10-31").status_code == 422
    missing = client.get("/api/exercise-records", headers=_bearer(token))
    assert missing.status_code == 422
