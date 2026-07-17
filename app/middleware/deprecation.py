from starlette.types import ASGIApp, Message, Receive, Scope, Send

# The original, pre-versioning paths (auth.py, users.py, admin.py, files.py,
# websocket.py mounted at root) — kept working indefinitely for backward
# compatibility, but new integrations should use /api/v1 instead. Deliberately
# excludes /health, /metrics, /, /docs, /redoc, /openapi.json — infrastructure
# endpoints aren't versioned.
_LEGACY_PREFIXES = ("/auth", "/users", "/admin", "/files", "/ws")
_SUCCESSOR_PREFIX = "/api/v1"
_SUNSET_DATE = "Wed, 31 Dec 2026 23:59:59 GMT"


class DeprecationHeadersMiddleware:
    """Marks responses from the legacy unversioned paths as deprecated via
    the Deprecation/Sunset headers (RFC 8594 + the deprecation-header
    convention widely used alongside it), pointing at the /api/v1 successor.
    See API Versioning in the README."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or not self._is_legacy_path(scope["path"]):
            await self.app(scope, receive, send)
            return

        successor = f"{_SUCCESSOR_PREFIX}{scope['path']}"

        async def send_wrapper(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = list(message.get("headers", []))
                headers.append((b"deprecation", b"true"))
                headers.append((b"sunset", _SUNSET_DATE.encode()))
                headers.append(
                    (
                        b"link",
                        f'<{successor}>; rel="successor-version"'.encode(),
                    )
                )
                message["headers"] = headers
            await send(message)

        await self.app(scope, receive, send_wrapper)

    @staticmethod
    def _is_legacy_path(path: str) -> bool:
        return any(
            path == prefix or path.startswith(f"{prefix}/")
            for prefix in _LEGACY_PREFIXES
        )
