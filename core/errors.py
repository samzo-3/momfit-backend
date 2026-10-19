"""공통 에러 응답 형식과 예외 핸들러.

모든 에러는 ``{"error": {"code", "message", "fields"?}}`` 형식으로 응답한다.
"""

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException


class AppError(Exception):
    """코드가 있는 애플리케이션 에러. 서비스 계층에서 발생시킨다."""

    def __init__(
        self,
        status_code: int,
        code: str,
        message: str,
        fields: dict[str, str] | None = None,
        headers: dict[str, str] | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message
        self.fields = fields
        self.headers = headers


def error_response(
    status_code: int,
    code: str,
    message: str,
    fields: dict[str, str] | None = None,
    headers: dict[str, str] | None = None,
) -> JSONResponse:
    """공통 형식의 에러 JSON 응답을 만든다."""
    error: dict[str, object] = {"code": code, "message": message}
    if fields:
        error["fields"] = fields
    return JSONResponse(status_code=status_code, content={"error": error}, headers=headers)


async def _handle_app_error(_: Request, exc: AppError) -> JSONResponse:
    return error_response(exc.status_code, exc.code, exc.message, exc.fields, exc.headers)


async def _handle_validation_error(
    _: Request, exc: RequestValidationError
) -> JSONResponse:
    fields: dict[str, str] = {}
    for item in exc.errors():
        # loc는 ("body", "password") 형태이며 맨 앞의 요청 위치는 제외한다.
        name = ".".join(str(part) for part in item["loc"][1:]) or str(item["loc"][0])
        fields.setdefault(name, item["msg"].removeprefix("Value error, "))
    return error_response(
        422, "VALIDATION_ERROR", "요청 값이 올바르지 않습니다.", fields
    )


async def _handle_http_exception(_: Request, exc: StarletteHTTPException) -> JSONResponse:
    # 404, 405 등 프레임워크가 발생시키는 에러도 같은 형식으로 맞춘다.
    return error_response(
        exc.status_code, f"HTTP_{exc.status_code}", str(exc.detail), headers=exc.headers
    )


def register_exception_handlers(app: FastAPI) -> None:
    """애플리케이션에 공통 예외 핸들러를 등록한다."""
    app.add_exception_handler(AppError, _handle_app_error)
    app.add_exception_handler(RequestValidationError, _handle_validation_error)
    app.add_exception_handler(StarletteHTTPException, _handle_http_exception)
