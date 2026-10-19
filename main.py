"""MomFit FastAPI 애플리케이션 진입점."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

import models  # noqa: F401  (create_all이 모든 모델을 알 수 있도록 import)
from api.health import router as health_router
from core.errors import register_exception_handlers
from db.base import Base
from db.session import engine


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    """시작할 때 없는 테이블을 만든다. (마이그레이션 도구는 도입하지 않았다)"""
    Base.metadata.create_all(bind=engine)
    yield


app = FastAPI(title="MomFit Backend", lifespan=lifespan)
register_exception_handlers(app)
app.include_router(health_router)
