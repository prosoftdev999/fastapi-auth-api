# fastapi-auth-api

[![CI](https://github.com/prosoftdev999/fastapi-auth-api/actions/workflows/ci.yml/badge.svg)](https://github.com/prosoftdev999/fastapi-auth-api/actions/workflows/ci.yml)
![Python 3.12](https://img.shields.io/badge/python-3.12-blue.svg)
![FastAPI](https://img.shields.io/badge/FastAPI-0.139-009688.svg)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

Production-ready FastAPI authentication API with JWT access/refresh tokens, email verification, password reset, PostgreSQL, Docker, structured logging, and automated tests.

## Features

- JWT authentication with short-lived access tokens and long-lived refresh tokens
- Email verification and password reset flows (token-based, time-limited, single-use — enforced via Redis)
- Logout with Redis-backed JWT blacklist (revokes access + refresh tokens immediately, not just at natural expiry)
- Redis-backed rate limiting on login/register/forgot-password (brute-force protection)
- OAuth login/signup and account linking for Google, GitHub, and Microsoft (Authlib), with password-optional accounts
- Role-based access control (admin / moderator / user) with a permission-dependency system gating admin endpoints
- Authenticated WebSockets (`/ws`) for private messaging and real-time notifications, with a Redis pub/sub bridge for multi-worker deployments
- Celery + Redis task queue: durable, retried email delivery; async report generation; a daily scheduled cleanup job
- Streaming file uploads (images/PDF/CSV/video) to S3-compatible storage, with size limits, magic-byte content validation, and a virus-scan hook
- API versioning (`/api/v1`, `/api/v2`) with the original unversioned paths kept working and marked deprecated, not removed
- PostgreSQL via SQLAlchemy 2.0 + Alembic migrations (auto-applied on deploy)
- Structured JSON logging with request-correlation IDs
- Centralized exception handling (never leaks stack traces to clients)
- Readiness health check with live database connectivity status
- CORS / trusted-host / GZip middleware, all environment-driven
- Environment-tiered configuration validation (dev stays permissive, production is strict)
- Dockerized, with a Render Blueprint for one-command deployment

## Tech Stack

Python 3.12 · FastAPI · SQLAlchemy 2.0 · Alembic · PostgreSQL · Redis · Celery · boto3/S3 · Authlib (OAuth) · Pydantic v2 · JWT (python-jose) · Gunicorn/Uvicorn · Nginx · Prometheus/Grafana · Pytest · Docker · GitHub Actions

## Quickstart

### With Docker Compose (recommended)

```bash
cp .env.example .env   # then fill in SECRET_KEY, SMTP_*, etc.
docker compose up --build
```

The API is now at `http://localhost:8000`, docs at `http://localhost:8000/docs`.

### Locally without Docker

```bash
python -m venv .venv
source .venv/Scripts/activate   # Windows Git Bash; use .venv/bin/activate on Linux/macOS
pip install -r requirements.txt
cp .env.example .env            # point DATABASE_URL/REDIS_URL at running Postgres/Redis instances
alembic upgrade head
uvicorn app.main:app --reload
```

## Configuration

Copy `.env.example` to `.env` and fill in the values. Settings are validated at startup (`app/core/config.py`):

- `ENVIRONMENT` — `development` | `test` | `staging` | `production`. Controls stricter validation below.
- `SECRET_KEY` — must be at least 16 characters always; at least 32 characters and not a known placeholder when `ENVIRONMENT=production`. Generate one with `openssl rand -hex 32`.
- In production, `DATABASE_URL` must not be SQLite, `FRONTEND_URL` must be `https://`, and `TRUSTED_HOSTS` must not be `*`.
- `CORS_ORIGINS` / `TRUSTED_HOSTS` / `TRUSTED_PROXY_IPS` accept comma-separated lists (or `*`).
- `DATABASE_URL` accepts both `postgresql+psycopg2://...` and bare `postgres://...` (auto-normalized — Render/Heroku hand out the latter).
- `TRUSTED_PROXY_IPS` — IPs/CIDRs of reverse proxies allowed to set `X-Forwarded-For`/`X-Forwarded-Proto` (empty by default, i.e. not trusted). See [Nginx, HTTPS, and security headers](#nginx-https-and-security-headers).
- `S3_*` — object storage for file uploads; unconfigured by default (`/files/*` returns `503` until `S3_ACCESS_KEY_ID`/`S3_SECRET_ACCESS_KEY` are set). See [File uploads](#file-uploads).

## API Examples

```bash
# Register
curl -X POST http://localhost:8000/auth/register \
  -H "Content-Type: application/json" \
  -d '{"email": "jane.doe@example.com", "password": "StrongPass123"}'

# Verify email (token arrives via the email sent on registration)
curl "http://localhost:8000/auth/verify-email?token=<verification_token>"

# Log in
curl -X POST http://localhost:8000/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email": "jane.doe@example.com", "password": "StrongPass123"}'
# -> {"access_token": "...", "refresh_token": "...", "token_type": "bearer"}

# Get the current user
curl http://localhost:8000/users/me \
  -H "Authorization: Bearer <access_token>"

# Refresh an access token
curl -X POST http://localhost:8000/auth/refresh \
  -H "Content-Type: application/json" \
  -d '{"refresh_token": "<refresh_token>"}'

# Forgot / reset password
curl -X POST http://localhost:8000/auth/forgot-password \
  -H "Content-Type: application/json" \
  -d '{"email": "jane.doe@example.com"}'

curl -X POST http://localhost:8000/auth/reset-password \
  -H "Content-Type: application/json" \
  -d '{"token": "<reset_token>", "new_password": "NewStrongPass456"}'

# Log out (blacklists the access token immediately; pass refresh_token to blacklist that too)
curl -X POST http://localhost:8000/auth/logout \
  -H "Authorization: Bearer <access_token>" \
  -H "Content-Type: application/json" \
  -d '{"refresh_token": "<refresh_token>"}'
```

Full interactive documentation (Swagger UI) is served at `/docs`, and ReDoc at `/redoc`, in every environment except production (see [Configuration](#configuration)). The examples above use the unversioned paths for brevity — see [API Versioning](#api-versioning) for the canonical `/api/v1`/`/api/v2` equivalents.

## API Versioning

Every route lives on three surfaces simultaneously — same handler, same database, same rate-limit budget, just different prefixes:

- **`/api/v1/...`** — the canonical, current API. Everything (`auth`, `users`, `oauth`, `admin`, `files`, `ws`) unchanged from how it's always behaved.
- **`/api/v2/...`** — evolves *only* what's actually changed so far: `GET/PATCH /api/v2/users/me` returns an extra `oauth_providers` field (previously a separate `GET /auth/oauth/accounts` call) — see `app/api/v2/users.py`. Everything else on `/api/v2` reuses the exact same v1 routers unchanged; a version bump doesn't require rewriting endpoints that didn't change.
- **The original unversioned paths** (`/auth/...`, `/users/...`, `/admin/...`, `/files/...`, `/ws`) — kept working indefinitely for callers written before versioning existed. `app.include_router(v1_router, deprecated=True)` in `app/main.py` mounts the *same* v1 router a second time, at the root, so there's exactly one implementation, not a forked copy to keep in sync.

**Deprecation strategy**: legacy (unversioned) responses carry `Deprecation: true`, `Sunset: <date>`, and `Link: <.../api/v1/...>; rel="successor-version"` headers (`app/middleware/deprecation.py`), and their OpenAPI entries render with strikethrough in Swagger UI (`deprecated=True`). Infrastructure endpoints (`/health`, `/metrics`, `/`, `/docs`) are deliberately excluded — they were never versioned to begin with. Nothing is ever silently removed; a path stops working only when its `Sunset` date arrives and it's explicitly dropped in a later change.

**Backward compatibility** is structural, not incidental: `/auth/register`, `/api/v1/auth/register`, and `/api/v2/auth/register` mount the identical `APIRouter` object (`app/api/v1/__init__.py`), so there's no risk of the versions drifting apart by accident — and they deliberately share one rate-limit bucket (keyed by scope, not path), so hitting three different prefixes for the same logical action isn't a way to triple your effective request budget.

The v1/v2 split for `/users/me` shares its actual logic (`update_user_email`/`change_user_password`/`deactivate_user` in `app/services/user_profile.py`) between both versions — the pattern to follow when a future v3 needs to evolve something else: extract the business logic once, let each version's router assemble the response shape it needs.

## OAuth (Google / GitHub / Microsoft)

Set the relevant `*_CLIENT_ID` / `*_CLIENT_SECRET` pair(s) in `.env` — each provider only activates once both are set. Register `<host>/auth/oauth/<provider>/callback` as the authorized redirect URI with the provider.

- `GET /auth/oauth/{provider}/login` — redirects to the provider; the callback logs in (creating a user on first login) and returns `TokenResponse` JSON, same shape as `/auth/login`.
- `GET /auth/oauth/{provider}/link` — requires `Authorization: Bearer <access_token>`; links the provider to the *current* user instead of creating a new one.
- `GET /auth/oauth/accounts` — lists the current user's linked providers.
- `DELETE /auth/oauth/{provider}` — unlinks a provider (rejected if it's the account's only sign-in method and no password is set).

OAuth-created accounts have no password until one is set via the password-reset flow — `hashed_password` is nullable for this reason.

## RBAC (roles & permissions)

Every new user gets the `user` role automatically. Three roles ship by default (seeded by the RBAC Alembic migration, and re-seeded per test run — see `app/core/rbac.py`):

| Role      | Permissions                                             |
|-----------|----------------------------------------------------------|
| `admin`     | `users:read`, `users:write`, `users:delete`, `roles:manage` |
| `moderator` | `users:read`, `users:write`                              |
| `user`      | *(none — regular account, acts only on itself)*          |

Routes are gated with `Depends(require_permissions("users:write"))` / `Depends(require_roles("admin"))` (`app/core/rbac.py`) — reusable dependency factories rather than a custom decorator, since FastAPI's dependency-injection system is the idiomatic place for this (a bare `@decorator` can't add `Depends`-resolved parameters or show up correctly in OpenAPI).

Admin endpoints (`tags=["Admin"]`):
- `GET /admin/users` — list users, paginated (`users:read`)
- `GET /admin/users/feed` — cursor-paginated user feed (`users:read`)
- `PATCH /admin/users/{id}` — update `is_active`/`is_verified` (`users:write`)
- `DELETE /admin/users/{id}` — deactivate a user (`users:delete`)
- `GET /admin/roles`, `POST /admin/users/{id}/roles`, `DELETE /admin/users/{id}/roles/{role}` (`roles:manage`)

There's no bootstrap endpoint for the first admin by design (an unauthenticated "make me admin" route would be a privilege-escalation hole) — grant it directly in the database: `INSERT INTO user_roles (user_id, role_id) SELECT <user_id>, id FROM roles WHERE name = 'admin';`

## WebSockets

`WS /ws?token=<access_token>` — one socket per connected client, authenticated the same way as everything else (JWT, checked against the same blacklist as HTTP requests via `get_current_user_ws` in `app/auth/dependencies.py`). Browsers can't set an `Authorization` header on a WebSocket handshake, so the token travels as a query param instead; a bad/missing/revoked token closes the connection with code `1008` before it's accepted.

Messages are JSON, multiplexed by a `type` field:
- Client → server: `{"type": "message", "to": <user_id>, "body": "..."}` — private message to another user.
- Server → client: `{"type": "message", "from": <user_id>, "body": "..."}`, or `{"type": "notification", "body": "..."}` pushed by other parts of the app (e.g. `/admin/users/{id}/roles` notifies the affected user immediately when a role is granted — see `app/api/admin.py`), or `{"type": "error", "detail": "..."}` for anything malformed.

`app/services/connection_manager.py` tracks only this worker process's live sockets in memory — with Gunicorn running multiple workers (`docker-compose.prod.yml`), a message for a user connected to a *different* worker won't reach them through that in-memory map alone. `app/services/ws_pubsub.py` bridges this: delivery tries the local connection first, and falls back to a Redis pub/sub publish (`ws:user:{id}` channels) that every worker's background listener (started via the app's `lifespan`) picks up and forwards locally if it holds that user's connection. Notification delivery is always best-effort and never raises — a Redis hiccup drops a live-push, it doesn't fail the request that triggered it.

## Background tasks (Celery)

Registration and password-reset emails, report generation, and a scheduled cleanup job all run on Celery workers (`app/core/celery_app.py`, Redis as both broker and result backend) rather than inline in the request or FastAPI's in-process `BackgroundTasks` — durable and retried, survives an API process restart, and doesn't hold a request open for slow work.

- **Email queue** (`app/tasks/email.py`) — `/auth/register` and `/auth/forgot-password` now call `.delay()` instead of sending synchronously or via `BackgroundTasks`. Each task retries up to 3 times (30s apart) on failure (e.g. SMTP hiccup) instead of silently dropping the email.
- **Report generation** (`app/tasks/reports.py`) — `POST /admin/reports/user-summary` (`users:read`) enqueues a user-count-by-role report and returns `202` with a `task_id` immediately; `GET /admin/reports/{task_id}` polls for the result. Demonstrates the standard "enqueue, return a handle, poll" pattern for anything too slow to compute inline.
- **Cleanup jobs** (`app/tasks/cleanup.py`) — `cleanup_unverified_users` deletes accounts that registered but never verified their email within 7 days (otherwise they permanently squat the email address, since registration checks for an existing row).
- **Task scheduler** — Celery Beat (`celery_app.conf.beat_schedule`) runs the cleanup job daily. `docker-compose.yml`/`docker-compose.prod.yml` run `celery_worker` and `celery_beat` as separate services — run exactly one `celery_beat` instance (it only schedules; running more would fire every job multiple times), scale `celery_worker` instances/concurrency freely.

Tests run tasks eagerly (synchronously, in the calling process, `celery_app.conf.task_always_eager = True` in `tests/conftest.py`) against an in-memory result backend and the same in-memory test database used everywhere else — no real Redis, broker, or worker process needed.

## File uploads

`POST /files/upload` (multipart form: `category` + `file`) streams to S3-compatible storage — `app/services/storage.py` uses `boto3`, configured via `S3_ENDPOINT_URL`/`S3_BUCKET_NAME`/`S3_REGION`/`S3_ACCESS_KEY_ID`/`S3_SECRET_ACCESS_KEY` (see [Configuration](#configuration)). Unconfigured (no access key/secret) returns `503`, same pattern as OAuth providers. `docker-compose.yml` runs a local MinIO instance by default so this works out of the box in dev without any real cloud account.

Four categories, each with its own allowed `Content-Type`s and size limit (`app/services/file_validation.py`):

| Category | Content-Types | Limit |
|----------|----------------|-------|
| `image` | jpeg, png, webp, gif | 10 MB |
| `pdf` | `application/pdf` | 20 MB |
| `csv` | `text/csv`, `application/vnd.ms-excel` | 20 MB |
| `video` | mp4, webm, quicktime | 200 MB |

**Streaming validation** (`read_and_validate_stream`) reads the upload in 1 MiB chunks — never holds the whole file in memory — enforcing the size limit and a magic-byte signature check (JPEG/PNG/GIF/WebP headers, `%PDF-`, MP4/MOV `ftyp` box, WebM header) against the *actual* file content, not just the client-supplied `Content-Type`, before it's ever handed to S3. CSV has no reliable magic bytes, so it's validated separately by actually parsing a sample instead (`validate_csv_content`). Once validation passes, the file is rewound and streamed on to S3 via `boto3`'s `upload_fileobj` (which multipart-uploads large files internally) — the file is read in full exactly twice (validate, then upload), never buffered whole into a single in-memory object either time.

**Virus scan placeholder** (`app/services/virus_scan.py`) — checked per-chunk during the same streaming pass. This is explicitly *not* a real virus scanner: it only recognizes the [EICAR test string](https://www.eicar.org/) (the industry-standard harmless string every real antivirus also flags), which exists so the reject-on-detection code path is exercised by something real rather than sitting completely untested. A production deployment must replace `scan_chunk_for_viruses` with a call to ClamAV (via `clamd`) or a cloud malware-scanning API.

`GET /files/` lists the current user's uploads (reuses the offset-pagination dependency from [Pagination](#pagination)); `GET /files/{id}` returns metadata plus a fresh presigned download URL (files are served via short-lived presigned S3 URLs, never proxied through the API); `DELETE /files/{id}` removes both the S3 object and the DB row. All three are scoped to the requesting user — a 404, not a 403, for someone else's file (doesn't confirm the ID exists).

Tests mock S3 entirely with [`moto`](https://github.com/getmoto/moto) (`@mock_aws`) — no real AWS/MinIO needed. `tests/conftest.py` sets dummy access-key/secret values so `is_storage_configured()` is `True`, and deliberately leaves `S3_ENDPOINT_URL` unset so boto3 targets the standard AWS endpoint pattern that moto intercepts.

## Pagination

Two reusable pagination dependencies live in `app/services/pagination.py` and are demonstrated on `/admin/users`:

- **Offset** (`GET /admin/users?limit=20&offset=0&sort=email&order=desc&q=jane&is_active=true`) — returns `Page[T]`: `{items, total, limit, offset, has_more}`. `sort` is restricted to an allowlist per resource (prevents sorting by arbitrary/unindexed columns); `q` searches via `ILIKE` over configured fields; extra filters (like `is_active`) are composed on top by the endpoint itself.
- **Cursor** (`GET /admin/users/feed?limit=20&cursor=<opaque>`) — keyset pagination on `id`, returns `CursorPage[T]`: `{items, next_cursor, has_more}`. Scales better than offset for large/growing tables since it doesn't `OFFSET`-scan skipped rows; `next_cursor` is `null` once there's nothing left.

Both dependencies are generic over the SQLAlchemy model and Pydantic response type, so adding pagination to a new resource is a few lines, not a new implementation.

## Production Docker

The `Dockerfile` is multi-stage: a `builder` stage compiles dependencies (needs `gcc` for `psycopg2`/`cryptography`), and the `runtime` stage copies only the resulting virtualenv plus app code — no compiler toolchain in the final image — and drops root via a dedicated `app` user. `docker-compose.yml` (dev) and Render both use this image's default CMD: a single Uvicorn process, which is enough for local dev and small/free-tier deploys.

For a real production host, use `docker-compose.prod.yml` instead — same image, but:
- overrides `command` to run **Gunicorn with Uvicorn workers** (`-k uvicorn.workers.UvicornWorker --workers ${WEB_CONCURRENCY:-4}`) for real concurrency across CPU cores
- no bind mounts, no dev conveniences
- Postgres/Redis have no host port mappings (only reachable from other containers on the compose network)
- per-service memory/CPU limits (`deploy.resources.limits`)
- secrets come from `.env.production` (gitignored — copy `.env.production.example` and fill it in); `POSTGRES_PASSWORD` has no default and compose refuses to start without it

```bash
cp .env.production.example .env.production   # fill in real secrets
docker compose -f docker-compose.prod.yml --env-file .env.production up --build
```

## Nginx, HTTPS, and security headers

`docker-compose.prod.yml` also runs Nginx as the sole public entrypoint (`api` itself has no host port mapping — only reachable from other containers), plus `certbot` for Let's Encrypt:

- **Reverse proxy** (`nginx/templates/default.conf.template`, env-substituted at container start via the official nginx image's templating) — terminates TLS, proxies to `api:8000`, sets `X-Forwarded-For`/`X-Forwarded-Proto`/`X-Real-IP`, gzip compression, and a `Cache-Control: immutable` location block for anything under `/static/`.
- **HTTPS** — first-time certificate issuance is a one-time bootstrap (`nginx/init-letsencrypt.sh`; handles the chicken-and-egg problem of Nginx needing a cert to start 443 before the ACME HTTP-01 challenge can run through it). The `certbot` service then renews automatically every 12h.
  ```bash
  DOMAIN=api.example.com EMAIL=admin@example.com ./nginx/init-letsencrypt.sh
  ```
- **Security headers** — set at *both* layers independently: Nginx (HSTS, `X-Content-Type-Options`, `X-Frame-Options`, `Referrer-Policy`) and the app itself (`app/middleware/security_headers.py`, added via `SecurityHeadersMiddleware`) so they're never missing even if one layer is bypassed or misconfigured. HSTS is only sent by the app when `ENVIRONMENT=production` — sending it in dev risks a browser caching an HTTPS-only policy for `localhost`.
- **Real client IPs behind the proxy** — `TRUSTED_PROXY_IPS` (see [Configuration](#configuration)) tells the app to trust `X-Forwarded-For` from Nginx via uvicorn's `ProxyHeadersMiddleware`, so the Redis rate limiter keys on the actual client IP instead of Nginx's container IP. Set to `*` here specifically because `api` has no other reachable path — a topology where it did would need this scoped to the real proxy IP/CIDR instead. Render's `render.yaml` sets the same, for the same reason (its edge proxy has no bypass path either).

## Monitoring

`docker-compose.prod.yml` runs a full observability stack alongside the app:

- **Application metrics** — `GET /metrics` (excluded from `/docs`/OpenAPI, no rate limit — Prometheus scrapes every 15s) via `prometheus-fastapi-instrumentator`: request rate/latency/status by handler, in-progress requests. Set up in `app/core/metrics.py`, wired in `main.py`.
- **Health metrics** — a `health_check_status` gauge (1=ok, 0=degraded) updated on every `GET /health` call, so "is the app healthy right now" is queryable in Prometheus/Grafana, not just via polling the endpoint directly.
- **Database metrics** — two angles: the app's own SQLAlchemy pool (`db_pool_size`, `db_pool_checked_out_connections`, sampled at scrape time via `Gauge.set_function`) and `postgres_exporter`, which exposes Postgres's own internal stats (connections, transaction rates, replication lag).
- **Docker/container metrics** — `cadvisor`, giving CPU/memory/network/disk per container.
- **Redis metrics** — `redis_exporter`, bonus alongside the above (Redis is load-bearing for rate limiting/blacklisting, worth watching).
- **Prometheus** (`monitoring/prometheus/prometheus.yml`) scrapes all of the above; **Grafana** comes with the Prometheus datasource auto-provisioned (`monitoring/grafana/provisioning/`) — log in and either build dashboards from the metric names above, or import a community one built for this exact instrumentator (e.g. grafana.com dashboard ID 16110, "FastAPI Observability").
- Structured JSON logging, request-correlation IDs, and centralized request/error logging were already built in Phase 1 (`app/core/logging.py`, `app/middleware/request_context.py`, `app/core/exceptions.py`) — nothing new needed here, they're the log-based half of observability that pairs with these metrics.

`prometheus`/`grafana` are exposed on `9090`/`3001` for convenience; put them behind a VPN/SSH tunnel/auth proxy in a real deployment rather than the open internet — Prometheus has no built-in auth.

## Deployment (Render)

`render.yaml` defines the web service and a managed PostgreSQL database (Render Blueprint spec).

1. In the Render dashboard: **New +** -> **Blueprint** -> select this repo.
2. Render provisions the Postgres database and wires `DATABASE_URL` automatically; `SECRET_KEY` is auto-generated.
3. Fill in the env vars marked `sync: false` in `render.yaml` (`REDIS_URL`, SMTP credentials, `FRONTEND_URL`, `CORS_ORIGINS`, `TRUSTED_HOSTS`) from the service's Environment tab — these are secrets/environment-specific and intentionally not committed. `REDIS_URL` needs a Redis instance provisioned separately (Render Key Value, Upstash, etc.).
4. Deploys run `alembic upgrade head` automatically before starting the server (see `Dockerfile`), and Render polls `/health` to decide when the new instance is ready to receive traffic.

> This repo isn't deployed yet — once you connect your Render account and deploy, add the live URL here.

## Project Structure

```
app/
  api/         # thin routers: auth.py, oauth.py, users.py, admin.py, websocket.py, files.py
    v1/        # aggregates the routers above under /api/v1 (and, deprecated, at root)
    v2/        # aggregates the same routers, except users.py -> its own evolved users.py
  auth/        # jwt.py, password.py, dependencies.py
  core/        # config.py, logging.py, exceptions.py, request_context.py, oauth.py, redis_client.py, rbac.py, metrics.py, celery_app.py
  db/          # session.py, base.py, init_db.py
  middleware/  # request_context.py (correlation ID + request logging), security_headers.py, deprecation.py
  models/      # SQLAlchemy ORM models (user.py, oauth_account.py, role.py, file_upload.py)
  schemas/     # Pydantic request/response models (user_v2.py holds the v2-only UserResponseV2)
  services/    # email.py, rate_limit.py, token_blacklist.py, connection_manager.py, ws_pubsub.py, storage.py, file_validation.py, virus_scan.py, user_profile.py (business logic)
  tasks/       # Celery tasks: email.py, reports.py, cleanup.py
migrations/    # Alembic revisions
tests/         # pytest suite (unit + integration, in-memory SQLite)
render.yaml    # Render Blueprint (web service + managed Postgres)
```

## Testing

```bash
pytest tests -v
```

Tests run against an in-memory SQLite database and a `fakeredis` in-memory Redis via dependency overrides (`tests/conftest.py`), so no external services are required.

## Screenshots

_Not yet captured — add a Swagger UI (`/docs`) screenshot here once the app is deployed or run locally._
