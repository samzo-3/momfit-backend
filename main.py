"""MomFit FastAPI 애플리케이션 진입점."""

from fastapi import FastAPI

from api.health import router as health_router
from core.errors import register_exception_handlers

app = FastAPI(title="MomFit Backend")
register_exception_handlers(app)
app.include_router(health_router)
