import asyncio
import contextlib
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, status
from fastapi.responses import JSONResponse
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session
from starlette.middleware.cors import CORSMiddleware
from starlette.middleware.gzip import GZipMiddleware
from starlette.middleware.trustedhost import TrustedHostMiddleware

from app.api.v1 import router as v1_router
from app.api.v2 import router as v2_router
from app.core.config import settings
from app.core.exceptions import register_exception_handlers
from app.core.logging import setup_logging
from app.core.metrics import health_check_status, setup_metrics
from app.db.session import get_db
from app.middleware.deprecation import DeprecationHeadersMiddleware
from app.middleware.request_context import RequestContextMiddleware
from app.middleware.security_headers import SecurityHeadersMiddleware
from app.schemas.health import HealthCheckDetail, HealthResponse
from app.services.ws_pubsub import run_pubsub_listener

setup_logging()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    pubsub_task = asyncio.create_task(run_pubsub_listener())
    try:
        yield
    finally:
        pubsub_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await pubsub_task

OPENAPI_TAGS = [
    {
        "name": "Health",
        "description": "Liveness/readiness probes used by deploy platforms and monitoring.",
    },
    {
        "name": "Authentication",
        "description": "Registration, login, token refresh, email verification, and password reset.",
    },
    {
        "name": "Users",
        "description": "Operations on the currently authenticated user's account.",
    },
    {
        "name": "OAuth",
        "description": "Login/signup and account linking via Google, GitHub, and Microsoft.",
    },
    {
        "name": "Admin",
        "description": "Role/permission-gated administrative operations on user accounts.",
    },
    {
        "name": "Files",
        "description": "Streaming uploads to S3-compatible storage (images, PDF, CSV, video).",
    },
]

app = FastAPI(
    title=settings.app_name,
    description="Authentication API with JWT, PostgreSQL, Docker, and tests.",
    version=settings.app_version,
    openapi_tags=OPENAPI_TAGS,
    contact={"name": "fastapi-auth-api", "url": "https://github.com/prosoftdev999/fastapi-auth-api"},
    license_info={"name": "MIT", "identifier": "MIT"},
    docs_url="/docs" if settings.docs_enabled else None,
    redoc_url="/redoc" if settings.docs_enabled else None,
    openapi_url="/openapi.json" if settings.docs_enabled else None,
    lifespan=lifespan,
)

register_exception_handlers(app)

# Middleware executes in reverse registration order (last added = outermost),
# so RequestContextMiddleware is added last to wrap the entire stack and
# capture/log every response, including ones rejected by CORS/TrustedHost.
app.add_middleware(GZipMiddleware, minimum_size=1000)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(TrustedHostMiddleware, allowed_hosts=settings.trusted_hosts)
app.add_middleware(SecurityHeadersMiddleware, hsts=settings.is_production)
app.add_middleware(DeprecationHeadersMiddleware)
app.add_middleware(RequestContextMiddleware)

# Canonical, versioned surface.
app.include_router(v1_router, prefix="/api/v1")
app.include_router(v2_router, prefix="/api/v2")

# Original unversioned paths, kept working for backward compatibility.
# deprecated=True marks them in OpenAPI (strikethrough in Swagger UI);
# DeprecationHeadersMiddleware above adds the corresponding response
# headers. See API Versioning in the README.
app.include_router(v1_router, deprecated=True)

setup_metrics(app)


@app.get("/", tags=["Health"])
async def root() -> dict[str, str]:
    return {
        "message": "FastAPI Authentication API is running",
        "status": "healthy",
    }


@app.get("/health", response_model=HealthResponse, tags=["Health"])
def health_check(db: Session = Depends(get_db)) -> JSONResponse:
    checks: dict[str, HealthCheckDetail] = {}

    try:
        db.execute(select(1))
        checks["database"] = HealthCheckDetail(status="ok")
    except SQLAlchemyError as exc:
        checks["database"] = HealthCheckDetail(status="error", error=str(exc))

    overall_status = (
        "ok"
        if all(check.status == "ok" for check in checks.values())
        else "degraded"
    )

    health_check_status.set(1 if overall_status == "ok" else 0)

    payload = HealthResponse(
        status=overall_status,
        version=settings.app_version,
        environment=settings.environment.value,
        checks=checks,
    )

    response_status = (
        status.HTTP_200_OK
        if overall_status == "ok"
        else status.HTTP_503_SERVICE_UNAVAILABLE
    )

    return JSONResponse(
        status_code=response_status,
        content=payload.model_dump(),
    )


# Only wraps when TRUSTED_PROXY_IPS is configured (production, behind Nginx).
# Rewrites scope["client"] from X-Forwarded-For so rate limiting and logging
# see the real client IP instead of the proxy's — must wrap last, after every
# route/middleware above is registered, since it replaces the ASGI callable
# uvicorn/gunicorn actually serves (`app.main:app`).
if settings.trusted_proxy_ips:
    from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware

    app = ProxyHeadersMiddleware(app, trusted_hosts=settings.trusted_proxy_ips)