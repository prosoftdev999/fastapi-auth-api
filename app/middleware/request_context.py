import logging
import time
import uuid

from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.core.request_context import reset_request_id, set_request_id

logger = logging.getLogger("app.request")

REQUEST_ID_HEADER = b"x-request-id"


class RequestContextMiddleware:
    """Assigns a correlation ID to every request and logs its completion.

    Pure ASGI (not BaseHTTPMiddleware) so streaming responses and exception
    propagation behave correctly, and so it can wrap the entire middleware
    stack including CORS/TrustedHost rejections.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        headers = dict(scope["headers"])
        incoming_id = headers.get(REQUEST_ID_HEADER)
        request_id = incoming_id.decode() if incoming_id else str(uuid.uuid4())

        token = set_request_id(request_id)
        start_time = time.perf_counter()
        status_code = 500

        async def send_wrapper(message: Message) -> None:
            nonlocal status_code

            if message["type"] == "http.response.start":
                status_code = message["status"]
                response_headers = list(message.get("headers", []))
                response_headers.append(
                    (REQUEST_ID_HEADER, request_id.encode())
                )
                message["headers"] = response_headers

            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        finally:
            duration_ms = round((time.perf_counter() - start_time) * 1000, 2)

            logger.info(
                "request completed",
                extra={
                    "http_method": scope.get("method"),
                    "http_path": scope.get("path"),
                    "http_status": status_code,
                    "duration_ms": duration_ms,
                },
            )

            reset_request_id(token)
