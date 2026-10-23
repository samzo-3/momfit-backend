"""환경 점검의 모델·입력·2D 규칙 임계값을 한 곳에서 관리한다."""

from dataclasses import dataclass


@dataclass(frozen=True)
class EnvironmentCheckSettings:
    # YOLO 모델명과 탐지 최소 신뢰도. 모델/규칙 조정 시 이 파일만 변경한다.
    model_name: str = "yolo11n.pt"
    confidence: float = 0.35
    # 업로드 DoS 방지와 너무 작은 프레임 판별 기준.
    max_image_bytes: int = 10 * 1024 * 1024
    min_image_dimension: int = 160
    allowed_image_types: frozenset[str] = frozenset({"image/jpeg", "image/png", "image/webp"})
    person_label: str = "person"
    min_person_frame_ratio: float = 0.08


SETTINGS = EnvironmentCheckSettings()
