"""일반 운동과 자세 배우기 모드가 공유하는 환경 점검 API."""
# 접수 창구 - React 요청을 받아 인증, 운동 조회, 분석 호출을 수행합니다.

from fastapi import APIRouter, Depends, File, Form, UploadFile
from sqlalchemy.orm import Session

from api.deps import get_onboarded_user
from core.errors import AppError
from db.session import get_db
from models.exercise import Exercise
from models.user import User
from schemas.environment_check import EnvironmentCheckResponse
from services.environment_check.analyzer import analyze_image, decode_image
from services.environment_check.detector import get_detector
from services.environment_check.profiles import profile_for_exercise_name

router = APIRouter(prefix="/api/environment-checks", tags=["environment-checks"])


@router.post("", response_model=EnvironmentCheckResponse)
async def check_environment(
    image: UploadFile = File(...),
    exercise_id: int = Form(..., ge=1),
    user: User = Depends(get_onboarded_user),
    db: Session = Depends(get_db),
) -> EnvironmentCheckResponse:
    """원본 이미지를 저장하지 않고 요청 수명 안에서만 검사한다.

    ``Depends``는 FastAPI가 호출 전에 인증 사용자와 DB 세션을 넣어 주는 방식이다.
    이 API는 온보딩 완료 사용자만 통과시키며, 선택한 운동의 ``exercise_id``가
    반드시 필요하다. 운동 모드는 받지 않는다. 일반 운동/자세 배우기 모두 같은
    운동 선택 결과로 이 API를 호출하기 때문이다.
    """
    _ = user
    exercise = db.get(Exercise, exercise_id)
    if exercise is None:
        raise AppError(404, "EXERCISE_NOT_FOUND", "운동을 찾을 수 없습니다.")
    # UploadFile은 multipart 파일을 나타낸다. 여기서 읽은 바이트는 DB나 디스크에 저장하지 않는다.
    content = await image.read()
    decoded = decode_image(content, image.content_type)
    try:
        # lru_cache로 보관된 프로세스 공용 모델을 가져온다. 요청마다 YOLO를 새로 만들지 않는다.
        detector = get_detector()
    except Exception as exc:
        raise AppError(503, "VISION_MODEL_UNAVAILABLE", "환경 점검 모델을 준비할 수 없습니다. 잠시 후 다시 시도해 주세요.") from exc
    return analyze_image(decoded, detector, profile_for_exercise_name(exercise.exercise_name))
