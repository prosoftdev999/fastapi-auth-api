from starlette.types import ASGIApp, Message, Receive, Scope, Send


class SecurityHeadersMiddleware:
    """Adds baseline security headers to every HTTP response.

    HSTS is opt-in (only meaningful — and safe to cache in browsers — once
    the deployment is actually served over HTTPS, i.e. behind the Nginx
    TLS-terminating reverse proxy in production).
    """

    def __init__(self, app: ASGIApp, *, hsts: bool = False) -> None:
        self.app = app
        self.hsts = hsts

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        async def send_wrapper(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = list(message.get("headers", []))
                headers.extend(self._security_headers())
                message["headers"] = headers
            await send(message)

        await self.app(scope, receive, send_wrapper)

    def _security_headers(self) -> list[tuple[bytes, bytes]]:
        headers = [
            (b"x-content-type-options", b"nosniff"),
            (b"x-frame-options", b"DENY"),
            (b"referrer-policy", b"strict-origin-when-cross-origin"),
            (
                b"permissions-policy",
                b"geolocation=(), microphone=(), camera=()",
            ),
        ]

        if self.hsts:
            headers.append(
                (
                    b"strict-transport-security",
                    b"max-age=63072000; includeSubDomains; preload",
                )
            )

        return headers
