"""voice_cues HTTP API 테스트. 실제 MySQL은 사용하지 않는다."""

from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.deps import get_onboarded_user
from api.voice_cues import router
from db.session import get_db
from services import voice_cue_service


@pytest.fixture
def client(monkeypatch):
    """인증과 DB를 대체한 독립 FastAPI 테스트 앱."""
    app = FastAPI()
    app.include_router(router)

    app.dependency_overrides[get_onboarded_user] = lambda: SimpleNamespace(id=1)
    app.dependency_overrides[get_db] = lambda: None

    def fake_get_voice_cues(
        db,
        *,
        category,
        exercise_id=None,
        exercise_step_id=None,
    ):
        now = datetime.now(timezone.utc)

        if category == "TRACKING":
            return [
                SimpleNamespace(
                    id=1,
                    exercise_id=None,
                    exercise_step_id=None,
                    category="TRACKING",
                    event_code="USER_LOST",
                    audio_url="/audio/pose/common/user_lost.mp3",
                    is_active=True,
                    message="화면 안으로 돌아와 주세요.",
                    created_at=now,
                    modified_at=now,
                )
            ]

        if category == "STUDY" and exercise_id == 1 and exercise_step_id == 3:
            return [
                SimpleNamespace(
                    id=2,
                    exercise_id=1,
                    exercise_step_id=3,
                    category="STUDY",
                    event_code="STEP_COMPLETED",
                    audio_url="/audio/pose/side-kick/step_completed.mp3",
                    is_active=True,
                    message="단계를 완료했습니다.",
                    created_at=now,
                    modified_at=now,
                )
            ]

        return []

    monkeypatch.setattr(
        voice_cue_service,
        "get_voice_cues",
        fake_get_voice_cues,
    )

    # 라우터는 함수를 직접 import하므로 라우터 모듈도 교체해야 한다.
    monkeypatch.setattr(
        "api.voice_cues.get_voice_cues",
        fake_get_voice_cues,
    )

    with TestClient(app) as test_client:
        yield test_client


def test_tracking_success(client):
    response = client.get("/api/voice-cues?category=TRACKING")

    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["event_code"] == "USER_LOST"


def test_study_step_success(client):
    response = client.get(
        "/api/voice-cues",
        params={
            "category": "STUDY",
            "exercise_id": 1,
            "exercise_step_id": 3,
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["exercise_step_id"] == 3


def test_exercise_empty_result(client):
    response = client.get(
        "/api/voice-cues",
        params={"category": "EXERCISE", "exercise_id": 1},
    )

    assert response.status_code == 200
    assert response.json() == []


@pytest.mark.parametrize(
    "params",
    [
        {"category": "INVALID"},
        {"category": "TRACKING", "exercise_id": 1},
        {"category": "EXERCISE", "exercise_id": 1, "exercise_step_id": 3},
        {"category": "STUDY", "exercise_step_id": 3},
        {"category": "STUDY", "exercise_id": -1},
        {"category": "STUDY", "exercise_id": 1, "exercise_step_id": 0},
    ],
)
def test_invalid_queries_return_422(client, params):
    response = client.get("/api/voice-cues", params=params)
    assert response.status_code == 422
