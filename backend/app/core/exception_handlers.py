from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.exceptions import AppError
from app.core.logging import logger
from app.schemas.errors import ErrorDetail, ErrorResponse, ValidationIssue


def _error_response(
    code: str,
    message: str,
    status_code: int,
    details: list[ValidationIssue] | None = None,
    headers: dict[str, str] | None = None,
) -> JSONResponse:
    payload = ErrorResponse(
        error=ErrorDetail(code=code, message=message, details=details)
    )
    return JSONResponse(
        status_code=status_code,
        content=payload.model_dump(mode="json", exclude_none=True),
        headers=headers,
    )


async def handle_app_error(_: Request, exc: AppError) -> JSONResponse:
    return _error_response(exc.code, exc.message, exc.status_code)


async def handle_http_error(
    _: Request, exc: StarletteHTTPException
) -> JSONResponse:
    message = exc.detail if isinstance(exc.detail, str) else "Request failed."
    return _error_response(
        "HTTP_ERROR",
        message,
        exc.status_code,
        headers=exc.headers,
    )


async def handle_validation_error(
    _: Request, exc: RequestValidationError
) -> JSONResponse:
    details = [
        ValidationIssue(
            location=list(issue["loc"]),
            message=issue["msg"],
            type=issue["type"],
        )
        for issue in exc.errors()
    ]
    return _error_response(
        "VALIDATION_ERROR",
        "Request validation failed.",
        422,
        details,
    )


async def handle_unexpected_error(request: Request, exc: Exception) -> JSONResponse:
    logger.exception(
        "Unhandled exception while handling %s %s",
        request.method,
        request.url.path,
        exc_info=(type(exc), exc, exc.__traceback__),
    )
    return _error_response(
        "INTERNAL_SERVER_ERROR",
        "An unexpected error occurred.",
        500,
    )


def register_exception_handlers(app: FastAPI) -> None:
    app.add_exception_handler(AppError, handle_app_error)
    app.add_exception_handler(StarletteHTTPException, handle_http_error)
    app.add_exception_handler(RequestValidationError, handle_validation_error)
    app.add_exception_handler(Exception, handle_unexpected_error)
