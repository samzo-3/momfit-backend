"""서비스 상태 확인 엔드포인트."""

from fastapi import APIRouter


router = APIRouter(prefix="/api", tags=["health"])


@router.get("/health")
def health_check() -> dict[str, str]:
    """서비스의 기본 상태를 반환한다."""
    return {"status": "ok"}
