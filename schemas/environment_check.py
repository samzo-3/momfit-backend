"""운동 전 카메라 환경 점검 API의 입출력 스키마."""

from enum import StrEnum

from pydantic import BaseModel, Field


class EnvironmentStatus(StrEnum):
    """PASS도 YOLO가 확인한 화면 범위 안의 결과일 뿐 실제 안전 보장은 아니다."""
    PASS = "PASS"
    NEEDS_ADJUSTMENT = "NEEDS_ADJUSTMENT"
    INCONCLUSIVE = "INCONCLUSIVE"


class BoundingBox(BaseModel):
    """원본(비반전) 프레임 기준의 픽셀 좌표다."""

    x1: float
    y1: float
    x2: float
    y2: float


class DetectedObject(BaseModel):
    """모델이 탐지한 COCO 객체 하나와 원본 프레임 bbox."""
    name: str
    confidence: float = Field(ge=0, le=1)
    bbox: BoundingBox


class EnvironmentCheckResponse(BaseModel):
    """프론트가 환경 점검 결과를 표시·진행 제어할 때 쓰는 응답 형식."""
    status: EnvironmentStatus
    can_continue: bool
    profile: str
    detections: list[DetectedObject]
    issue_codes: list[str]
    messages: list[str]
