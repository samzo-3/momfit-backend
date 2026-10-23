"""챗봇 서비스로 요청을 전달하는 프록시.

챗봇은 별도 서비스(momfit-chatbot)이고, 클러스터 Ingress는 /api 전체를 백엔드로 보낸다.
그래서 프론트가 부르는 /api/chat/*을 백엔드가 받아 챗봇에 그대로 넘긴다.
인증은 여기서 한 번 확인하고(백엔드 JWT), 챗봇은 같은 토큰으로 /api/users/me를 다시 불러 사용자와 임신 주수를 얻는다.
사용자당 호출 제한은 챗봇이 센다. 챗봇의 상태·에러 응답(401, 429 등)은 바꾸지 않고 전달한다.
"""

import logging
from functools import lru_cache
from typing import Annotated

import httpx
from fastapi import APIRouter, Depends, Request, Response

from api.deps import get_onboarded_user
from core.config import settings
from core.errors import AppError
from models.user import User

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/chat", tags=["chat"])

# 챗봇 응답 중 클라이언트에 그대로 돌려주는 헤더. Retry-After는 호출 제한(429)에서 쓴다.
_PASSTHROUGH_HEADERS = ("content-type", "retry-after")


@lru_cache
def get_chatbot_client() -> httpx.AsyncClient:
    """챗봇용 HTTP 클라이언트. 프로세스에서 하나만 만들어 연결을 재사용한다."""
    return httpx.AsyncClient(
        base_url=settings.chatbot_url,
        timeout=httpx.Timeout(settings.chatbot_timeout_seconds, connect=5.0),
    )


async def _forward(
    client: httpx.AsyncClient,
    method: str,
    path: str,
    *,
    headers: dict[str, str] | None = None,
    content: bytes | None = None,
) -> Response:
    try:
        upstream = await client.request(method, path, headers=headers, content=content)
    except httpx.HTTPError as exc:
        # 질문 내용은 로그에 남기지 않는다. 챗봇이 죽어도 백엔드의 다른 API는 영향을 받지 않는다.
        logger.warning("챗봇 서비스 호출에 실패했습니다: %s", type(exc).__name__)
        raise AppError(
            503, "SERVICE_UNAVAILABLE", "지금은 답변을 만들 수 없어요. 잠시 후 다시 시도해 주세요."
        ) from exc
    return Response(
        content=upstream.content,
        status_code=upstream.status_code,
        headers={
            name: upstream.headers[name]
            for name in _PASSTHROUGH_HEADERS
            if name in upstream.headers
        },
    )


@router.post("/messages")
async def send_message(
    request: Request,
    _: Annotated[User, Depends(get_onboarded_user)],
    client: Annotated[httpx.AsyncClient, Depends(get_chatbot_client)],
) -> Response:
    """질문을 챗봇에 전달하고 답을 그대로 돌려준다. 본문 검증(길이 등)은 챗봇이 한다."""
    return await _forward(
        client,
        "POST",
        "/api/chat/messages",
        headers={
            "Authorization": request.headers.get("Authorization", ""),
            "Content-Type": request.headers.get("Content-Type", "application/json"),
        },
        content=await request.body(),
    )


@router.get("/health")
async def chatbot_health(
    client: Annotated[httpx.AsyncClient, Depends(get_chatbot_client)],
) -> Response:
    """챗봇 프로세스 상태. 운영 점검용이라 인증 없이 열어 둔다."""
    return await _forward(client, "GET", "/api/chat/health")


@router.get("/ready")
async def chatbot_ready(
    client: Annotated[httpx.AsyncClient, Depends(get_chatbot_client)],
) -> Response:
    """챗봇과 벡터 DB 연결 상태. 운영 점검용이라 인증 없이 열어 둔다."""
    return await _forward(client, "GET", "/api/chat/ready")
