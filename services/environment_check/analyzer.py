"""이미지 검증, 탐지 호출, 규칙 결과 조립을 분리한다."""
# 처리 담당 - 이미지 분석과 환경 규칙 적용을 연결하고 결과를 조립

from io import BytesIO

from PIL import Image, UnidentifiedImageError

from core.errors import AppError
from services.environment_check.config import SETTINGS
from schemas.environment_check import BoundingBox, DetectedObject, EnvironmentCheckResponse
from services.environment_check.detector import Detector
from services.environment_check.profiles import EnvironmentProfile
from services.environment_check.rules import evaluate

def decode_image(content: bytes, content_type: str | None) -> Image.Image:
    """업로드 바이트를 검증하고, YOLO가 받는 RGB 이미지로만 변환한다."""
    if content_type not in SETTINGS.allowed_image_types:
        raise AppError(422, "INVALID_IMAGE_TYPE", "JPEG, PNG 또는 WebP 이미지가 필요합니다.")
    if not content or len(content) > SETTINGS.max_image_bytes:
        raise AppError(422, "INVALID_IMAGE_SIZE", "이미지 크기는 1바이트 이상 10MB 이하여야 합니다.")
    try:
        image = Image.open(BytesIO(content))
        image.verify()
        image = Image.open(BytesIO(content)).convert("RGB")
    except (UnidentifiedImageError, OSError, ValueError) as exc:
        raise AppError(422, "INVALID_IMAGE", "읽을 수 없는 이미지입니다.") from exc
    if image.width < SETTINGS.min_image_dimension or image.height < SETTINGS.min_image_dimension:
        raise AppError(422, "INVALID_IMAGE_RESOLUTION", "이미지는 가로·세로 160px 이상이어야 합니다.")
    return image


def analyze_image(image: Image.Image, detector: Detector, profile: EnvironmentProfile) -> EnvironmentCheckResponse:
    """탐지(Detector)와 안전 판단(rules)을 분리해 테스트·교체 가능하게 유지한다."""
    try:
        detections = detector.detect(image)
    except Exception as exc:
        raise AppError(503, "VISION_INFERENCE_FAILED", "환경 점검 모델을 실행할 수 없습니다. 잠시 후 다시 시도해 주세요.") from exc
    result = evaluate(detections, image.size, profile)
    # Pydantic 응답 모델을 거쳐 API 응답 필드 형식도 함께 검증한다.
    return EnvironmentCheckResponse(
        status=result.status,
        can_continue=result.status == "PASS",
        profile=profile.name,
        detections=[DetectedObject(name=item.name, confidence=item.confidence, bbox=BoundingBox(x1=item.bbox[0], y1=item.bbox[1], x2=item.bbox[2], y2=item.bbox[3])) for item in detections],
        issue_codes=result.issue_codes,
        messages=result.messages,
    )
