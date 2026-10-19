"""MomFit FastAPI 애플리케이션 진입점."""

from fastapi import FastAPI

from api.health import router as health_router

app = FastAPI(title="MomFit Backend")
app.include_router(health_router)
