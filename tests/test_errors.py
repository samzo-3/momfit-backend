from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import BaseModel, Field, field_validator

from core.errors import AppError, register_exception_handlers


class _Body(BaseModel):
    password: str = Field(min_length=8)


class _Nickname(BaseModel):
    nickname: str

    @field_validator("nickname")
    @classmethod
    def _not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("닉네임을 입력해 주세요.")
        return value


def _create_app() -> FastAPI:
    app = FastAPI()
    register_exception_handlers(app)

    @app.get("/app-error")
    def app_error() -> None:
        raise AppError(401, "INVALID_CREDENTIALS", "아이디 또는 비밀번호가 올바르지 않습니다.")

    @app.get("/app-error-headers")
    def app_error_headers() -> None:
        raise AppError(429, "RATE_LIMITED", "잠시 후 다시 시도해 주세요.", headers={"Retry-After": "60"})

    @app.post("/validate")
    def validate(body: _Body) -> None:
        return None

    @app.post("/nickname")
    def nickname(body: _Nickname) -> None:
        return None

    return app


client = TestClient(_create_app())


def test_AppError는_공통_형식으로_응답한다() -> None:
    response = client.get("/app-error")

    assert response.status_code == 401
    assert response.json() == {
        "error": {
            "code": "INVALID_CREDENTIALS",
            "message": "아이디 또는 비밀번호가 올바르지 않습니다.",
        }
    }


def test_AppError의_헤더가_응답에_포함된다() -> None:
    response = client.get("/app-error-headers")

    assert response.status_code == 429
    assert response.headers["Retry-After"] == "60"


def test_검증_오류는_422와_필드별_메시지를_반환한다() -> None:
    response = client.post("/validate", json={"password": "short"})

    assert response.status_code == 422
    error = response.json()["error"]
    assert error["code"] == "VALIDATION_ERROR"
    assert "password" in error["fields"]


def test_본문이_없으면_검증_오류로_응답한다() -> None:
    response = client.post("/validate")

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


def test_존재하지_않는_경로도_공통_형식이다() -> None:
    response = client.get("/nope")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "HTTP_404"


def test_검증_메시지에서_pydantic_접두사를_제거한다() -> None:
    response = client.post("/nickname", json={"nickname": "  "})

    assert response.json()["error"]["fields"] == {"nickname": "닉네임을 입력해 주세요."}
