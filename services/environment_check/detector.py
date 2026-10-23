"""Ultralytics 추론을 앱 프로세스에서 한 번만 로드하는 어댑터."""
# YOLO로 사람과 주변 객체를 인식합니다.


from dataclasses import dataclass
from functools import lru_cache
from typing import Protocol

from services.environment_check.config import SETTINGS


@dataclass(frozen=True)
class Detection:
    name: str
    confidence: float
    # x1, y1, x2, y2. 항상 원본(비반전) 이미지 픽셀 기준이다.
    bbox: tuple[float, float, float, float]


class Detector(Protocol):
    """YOLO 외의 탐지기나 테스트용 FakeDetector도 따를 수 있는 최소 인터페이스."""

    def detect(self, image: object) -> list[Detection]: ...


class UltralyticsDetector:
    def __init__(self) -> None:
        try:
            from ultralytics import YOLO
        except ImportError as exc:  # vision extras를 설치하지 않은 기본 서버
            raise RuntimeError("VISION_DEPENDENCY_MISSING") from exc
        self._model = YOLO(SETTINGS.model_name)

    def detect(self, image: object) -> list[Detection]:
        """Ultralytics 결과를 앱 내부의 단순 Detection 형식으로 변환한다."""
        result = self._model(image, conf=SETTINGS.confidence, verbose=False)[0]
        names = result.names
        detections: list[Detection] = []
        for box in result.boxes:
            class_id = int(box.cls[0].item())
            x1, y1, x2, y2 = (float(value) for value in box.xyxy[0].tolist())
            detections.append(
                Detection(
                    name=str(names[class_id]),
                    confidence=float(box.conf[0].item()),
                    bbox=(x1, y1, x2, y2),
                )
            )
        return detections


@lru_cache(maxsize=1)
def get_detector() -> Detector:
    """요청마다 모델을 재로딩하지 않는 프로세스 단위 싱글턴."""
    return UltralyticsDetector()
