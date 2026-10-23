"""MomFit FastAPI 애플리케이션 진입점."""

import asyncio
from api.sidekick_study import router as sidekick_study_router
from api.environment_checks import router as environment_checks_router
from api.voice_cues import router as voice_cues_router
from api.exercise_step_records import router as exercise_step_records_router
from api.exercise_records import router as exercise_records_router
import contextlib
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

import models  # noqa: F401  (create_all이 모든 모델을 알 수 있도록 import)
from api.agent.daily_report import router as agent_router
from api.auth import router as auth_router
from api.health import router as health_router
from api.kakao_auth import router as kakao_auth_router
from api.users import router as users_router
from core.config import settings
from core.errors import register_exception_handlers
from db.base import Base
from db.session import engine
from services.auth.account_service import run_purge

logger = logging.getLogger(__name__)


async def _purge_periodically(interval_hours: int) -> None:
    """유예 기간이 지난 탈퇴 계정을 주기적으로 삭제한다. 한 번 실패해도 다음 주기에 다시 시도한다."""
    while True:
        try:
            await asyncio.to_thread(run_purge)
        except Exception:
            logger.exception("탈퇴 계정 삭제 작업에 실패했습니다.")
        await asyncio.sleep(interval_hours * 60 * 60)


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    """시작할 때 없는 테이블을 만들고, 탈퇴 계정 삭제 주기 작업을 시작한다.

    (마이그레이션 도구는 도입하지 않았다. 서버를 여러 개 띄워도 삭제는 중복 실행에 안전하다.)
    """
    Base.metadata.create_all(bind=engine)
    purge_task = None
    if settings.account_purge_interval_hours > 0:
        purge_task = asyncio.create_task(
            _purge_periodically(settings.account_purge_interval_hours)
        )
    yield
    if purge_task is not None:
        purge_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await purge_task


app = FastAPI(title="MomFit Backend", lifespan=lifespan)
register_exception_handlers(app)
app.include_router(health_router)
app.include_router(auth_router)
app.include_router(kakao_auth_router)
app.include_router(users_router)
app.include_router(agent_router)

app.include_router(voice_cues_router)
app.include_router(exercise_step_records_router)
app.include_router(exercise_records_router)
app.include_router(sidekick_study_router)
app.include_router(environment_checks_router)
