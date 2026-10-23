from io import BytesIO
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from PIL import Image

from api.deps import get_onboarded_user
from api.environment_checks import router
from core.errors import register_exception_handlers
from db.session import get_db
from models.exercise import Exercise
from services.environment_check.detector import Detection


def image_file():
    output = BytesIO()
    Image.new("RGB", (1000, 800)).save(output, "JPEG")
    return ("camera.jpg", output.getvalue(), "image/jpeg")


class FakeDetector:
    def detect(self, image):
        return [Detection("person", .95, (300, 100, 600, 700)), Detection("chair", .8, (20, 100, 200, 700))]


@pytest.fixture
def client(monkeypatch):
    app = FastAPI()
    register_exception_handlers(app)
    app.include_router(router)
    app.dependency_overrides[get_onboarded_user] = lambda: SimpleNamespace(id=1)
    app.dependency_overrides[get_db] = lambda: SimpleNamespace(
        get=lambda model, identifier: SimpleNamespace(exercise_name="Side Kick") if identifier == 1 else None
    )
    monkeypatch.setattr("api.environment_checks.get_detector", lambda: FakeDetector())
    with TestClient(app) as test_client:
        yield test_client


def test_api_returns_schema_and_default_profile(client):
    response = client.post("/api/environment-checks", data={"exercise_id": "1"}, files={"image": image_file()})
    assert response.status_code == 200
    assert response.json()["status"] == "PASS"
    assert response.json()["profile"] == "default"
    assert response.json()["detections"][0]["bbox"]["x1"] == 300


def test_api_rejects_invalid_image(client):
    response = client.post("/api/environment-checks", data={"exercise_id": "1"}, files={"image": ("bad.gif", b"bad", "image/gif")})
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "INVALID_IMAGE_TYPE"


def test_api_reports_model_loading_failure(client, monkeypatch):
    monkeypatch.setattr("api.environment_checks.get_detector", lambda: (_ for _ in ()).throw(RuntimeError()))
    response = client.post("/api/environment-checks", data={"exercise_id": "1"}, files={"image": image_file()})
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "VISION_MODEL_UNAVAILABLE"


def test_side_kick_uses_default_policy_not_side_step_policy(client):
    response = client.post("/api/environment-checks", data={"exercise_id": "1"}, files={"image": image_file()})
    assert response.status_code == 200
    assert response.json()["profile"] == "default"


def test_unregistered_exercise_id_returns_404(client):
    response = client.post("/api/environment-checks", data={"exercise_id": "999"}, files={"image": image_file()})
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "EXERCISE_NOT_FOUND"


def test_exercise_id_is_required_for_shared_mode_contract(client):
    response = client.post("/api/environment-checks", files={"image": image_file()})
    assert response.status_code == 422
