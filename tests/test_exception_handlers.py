import asyncio
import json

from fastapi.exceptions import RequestValidationError
from fastapi.testclient import TestClient
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.requests import Request

from app.core.exceptions import (
    handle_http_exception,
    handle_unhandled_exception,
    handle_validation_error,
)


def make_request(path: str = "/test", method: str = "GET") -> Request:
    scope = {
        "type": "http",
        "method": method,
        "path": path,
        "headers": [],
        "query_string": b"",
        "client": ("testclient", 50000),
        "server": ("testserver", 80),
        "scheme": "http",
    }
    return Request(scope)


def test_http_exception_handler_preserves_default_shape() -> None:
    request = make_request()
    exc = StarletteHTTPException(status_code=404, detail="Not found")

    response = asyncio.run(handle_http_exception(request, exc))

    assert response.status_code == 404
    assert json.loads(response.body) == {"detail": "Not found"}


def test_http_exception_handler_preserves_custom_headers() -> None:
    request = make_request()
    exc = StarletteHTTPException(
        status_code=401,
        detail="Invalid credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )

    response = asyncio.run(handle_http_exception(request, exc))

    assert response.headers["www-authenticate"] == "Bearer"


def test_unhandled_exception_handler_returns_generic_500() -> None:
    request = make_request()
    exc = RuntimeError("boom")

    response = asyncio.run(handle_unhandled_exception(request, exc))

    assert response.status_code == 500
    assert json.loads(response.body) == {"detail": "Internal Server Error"}


def test_validation_error_handler_returns_422() -> None:
    request = make_request()
    exc = RequestValidationError(errors=[])

    response = asyncio.run(handle_validation_error(request, exc))

    assert response.status_code == 422


def test_unknown_route_is_handled_through_registered_handler(
    client: TestClient,
) -> None:
    response = client.get("/definitely-not-a-route")

    assert response.status_code == 404
    assert response.json() == {"detail": "Not Found"}
