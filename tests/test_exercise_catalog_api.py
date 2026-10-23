"""신규 범용 운동 카탈로그 및 STEP 시작 식별자 API 계약."""

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from models.exercise import Exercise
from models.exercise_criteria_version import ExerciseCriteriaVersion
from models.exercise_step import ExerciseStep
from models.exercise_step_criteria_version import ExerciseStepCriteriaVersion
from tests.helpers import signup_payload


def _token(client: TestClient) -> str:
    response = client.post("/api/auth/signup", json=signup_payload())
    assert response.status_code == 201
    return response.json()["access_token"]


def _headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _seed(db: Session) -> None:
    exercise = Exercise(id=10, exercise_name="Side Step", video_url="/side-step.mp4")
    steps = [
        ExerciseStep(id=101, exercise_id=10, step_order=1, step_name="READY", clip_video_url="/ready.mp4", important=True),
        ExerciseStep(id=102, exercise_id=10, step_order=2, step_name="RIGHT", clip_video_url="/right.mp4", important=True),
    ]
    parent = {
        "measurement_profile_version": "profile-v1",
        "mapping_rule_version": "mapping-v1",
        "steps": [
            {"step_order": 1, "step_code": "READY", "step_criteria_version": "s1", "criteria": {"enabled": False}},
            {"step_order": 2, "step_code": "RIGHT", "step_criteria_version": "s1", "criteria": {"enabled": True}},
        ],
    }
    version = ExerciseCriteriaVersion(id=201, exercise_id=10, evaluation_criteria=parent, criteria_version="v1", schema_version=1, status="ACTIVE")
    children = [
        ExerciseStepCriteriaVersion(id=301, exercise_step_id=101, exercise_criteria_version_id=201, step_criteria_version="s1", evaluation_criteria={"enabled": False}),
        ExerciseStepCriteriaVersion(id=302, exercise_step_id=102, exercise_criteria_version_id=201, step_criteria_version="s1", evaluation_criteria={"enabled": True}),
    ]
    db.add_all([exercise, *steps, version, *children])
    db.commit()


def test_catalog_and_fixed_criteria_version_are_read_from_db(client: TestClient, db_session: Session) -> None:
    _seed(db_session)
    headers = _headers(_token(client))

    assert client.get("/api/exercises", headers=headers).json()[0]["id"] == 10
    assert client.get("/api/exercises/10/steps", headers=headers).json()[1]["id"] == 102
    active = client.get("/api/exercises/10/criteria/active", headers=headers)
    fixed = client.get("/api/exercises/10/criteria/201", headers=headers)

    assert active.status_code == fixed.status_code == 200
    assert active.json()["id"] == fixed.json()["id"] == 201
    assert active.json()["steps"][0]["evaluation_criteria"] == {"enabled": False}


def test_active_criteria_rejects_multiple_active_versions(client: TestClient, db_session: Session) -> None:
    _seed(db_session)
    db_session.add(ExerciseCriteriaVersion(id=202, exercise_id=10, evaluation_criteria={}, criteria_version="v2", schema_version=1, status="ACTIVE"))
    db_session.commit()

    response = client.get("/api/exercises/10/criteria/active", headers=_headers(_token(client)))

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "MULTIPLE_ACTIVE_EXERCISE_CRITERIA"
