"""운동 및 사용자 추적 음성 안내 조회 API."""

from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from api.deps import get_onboarded_user
from db.session import get_db
from models.user import User
from schemas.voice_cue import VoiceCueResponse
from services.pose_coaching.voice_cue_service import get_voice_cues


router = APIRouter(prefix="/api/voice-cues", tags=["voice-cues"])

VoiceCategory = Literal["TRACKING", "EXERCISE", "STUDY"]


@router.get("", response_model=list[VoiceCueResponse])
def list_voice_cues(
    category: VoiceCategory,
    exercise_id: Annotated[int | None, Query(gt=0)] = None,
    exercise_step_id: Annotated[int | None, Query(gt=0)] = None,
    user: User = Depends(get_onboarded_user),
    db: Session = Depends(get_db),
) -> list[VoiceCueResponse]:
    """현재 운동·STEP에 적용되는 활성 음성 목록을 반환한다."""

    # 이미 인증 및 온보딩 검사를 통과한 사용자
    _ = user

    # STEP을 요청할 때는 운동 ID도 반드시 필요하다.
    if exercise_step_id is not None and exercise_id is None:
        from fastapi import HTTPException

        raise HTTPException(
            status_code=422,
            detail="exercise_step_id를 지정하려면 exercise_id도 필요합니다.",
        )

    # TRACKING은 모든 운동에 공통으로 사용하는 음성이다.
    if category == "TRACKING":
        if exercise_id is not None or exercise_step_id is not None:
            from fastapi import HTTPException

            raise HTTPException(
                status_code=422,
                detail="TRACKING에는 운동 및 STEP ID를 지정할 수 없습니다.",
            )

    # 일반 운동 모드에서는 STEP ID를 사용하지 않는다.
    if category == "EXERCISE" and exercise_step_id is not None:
        from fastapi import HTTPException

        raise HTTPException(
            status_code=422,
            detail="EXERCISE에는 STEP ID를 지정할 수 없습니다.",
        )

    cues = get_voice_cues(
        db,
        category=category,
        exercise_id=exercise_id,
        exercise_step_id=exercise_step_id,
    )

    return [VoiceCueResponse.model_validate(cue) for cue in cues]
