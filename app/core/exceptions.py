import logging

from fastapi import FastAPI, Request, status
from fastapi.exception_handlers import (
    http_exception_handler as default_http_exception_handler,
)
from fastapi.exception_handlers import (
    request_validation_exception_handler as default_validation_exception_handler,
)
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

logger = logging.getLogger("app.errors")


async def handle_http_exception(
    request: Request, exc: StarletteHTTPException
) -> JSONResponse:
    logger.warning(
        "http exception",
        extra={
            "http_method": request.method,
            "http_path": request.url.path,
            "http_status": exc.status_code,
            "detail": exc.detail,
        },
    )
    return await default_http_exception_handler(request, exc)


async def handle_validation_error(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    logger.warning(
        "request validation failed",
        extra={
            "http_method": request.method,
            "http_path": request.url.path,
            "errors": exc.errors(),
        },
    )
    return await default_validation_exception_handler(request, exc)


async def handle_unhandled_exception(
    request: Request, exc: Exception
) -> JSONResponse:
    logger.error(
        "unhandled exception",
        exc_info=exc,
        extra={
            "http_method": request.method,
            "http_path": request.url.path,
        },
    )
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"detail": "Internal Server Error"},
    )


def register_exception_handlers(app: FastAPI) -> None:
    app.add_exception_handler(StarletteHTTPException, handle_http_exception)
    app.add_exception_handler(RequestValidationError, handle_validation_error)
    app.add_exception_handler(Exception, handle_unhandled_exception)
