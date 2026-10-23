from io import BytesIO
import pytest
from PIL import Image
from core.errors import AppError
from services.environment_check.analyzer import analyze_image, decode_image
from services.environment_check.detector import Detection
from services.environment_check.profiles import DEFAULT_PROFILE


class FakeDetector:
    def __init__(self, detections=None, error=None): self.detections, self.error = detections or [], error
    def detect(self, image):
        if self.error: raise self.error
        return self.detections


def jpeg_bytes(size=(200, 200)):
    output = BytesIO(); Image.new("RGB", size).save(output, "JPEG"); return output.getvalue()


def test_decode_image_validates_input():
    assert decode_image(jpeg_bytes(), "image/jpeg").size == (200, 200)
    with pytest.raises(AppError): decode_image(jpeg_bytes(), "image/gif")
    with pytest.raises(AppError): decode_image(jpeg_bytes((100, 100)), "image/jpeg")
    with pytest.raises(AppError): decode_image(b"not-an-image", "image/jpeg")


def test_inference_error_is_app_error():
    with pytest.raises(AppError) as raised: analyze_image(Image.new("RGB", (200, 200)), FakeDetector(error=RuntimeError()), DEFAULT_PROFILE)
    assert raised.value.code == "VISION_INFERENCE_FAILED"


def test_analyzer_returns_raw_bbox_and_object_name():
    response = analyze_image(Image.new("RGB", (1000, 800)), FakeDetector([Detection("person", .95, (300, 100, 600, 700)), Detection("bed", .8, (20, 100, 200, 700))]), DEFAULT_PROFILE)
    assert response.status == "PASS"
    assert response.can_continue is True
    assert response.detections[1].bbox.x1 == 20


@pytest.mark.parametrize(
    ("detections", "expected_status"),
    [
        ([], "INCONCLUSIVE"),
        ([Detection("person", .95, (100, 100, 500, 700)), Detection("person", .95, (550, 100, 900, 700))], "NEEDS_ADJUSTMENT"),
    ],
)
def test_non_pass_result_cannot_start_exercise(detections, expected_status):
    response = analyze_image(Image.new("RGB", (1000, 800)), FakeDetector(detections), DEFAULT_PROFILE)
    assert response.status == expected_status
    assert response.can_continue is False
