"""네트워크/모델 가중치가 필요한 실제 YOLO 연동 테스트.

기본 테스트에서는 다운로드하지 않는다. ``RUN_VISION_INTEGRATION=1``일 때만
vision extras가 설치된 환경에서 실행한다.
"""

import os

import pytest
from PIL import Image

from services.environment_check.detector import get_detector


pytestmark = pytest.mark.skipif(
    os.getenv("RUN_VISION_INTEGRATION") != "1",
    reason="RUN_VISION_INTEGRATION=1일 때만 모델 다운로드/실제 YOLO 추론을 실행합니다.",
)


def test_yolo_runs_on_one_image():
    image = Image.new("RGB", (640, 480), "white")
    detections = get_detector().detect(image)
    assert isinstance(detections, list)
    assert all(len(item.bbox) == 4 and 0 <= item.confidence <= 1 for item in detections)
