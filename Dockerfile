# ---- builder: compile deps into a venv, including build-time tooling ----
FROM python:3.12-slim AS builder

WORKDIR /app

RUN apt-get update \
 && apt-get install -y --no-install-recommends gcc \
 && rm -rf /var/lib/apt/lists/*

RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

COPY requirements.txt .

RUN pip install --no-cache-dir --upgrade pip \
 && pip install --no-cache-dir -r requirements.txt

# ---- runtime: no compilers, no build tooling, non-root user ----
FROM python:3.12-slim AS runtime

WORKDIR /app

RUN groupadd --system app \
 && useradd --system --gid app --home-dir /app --no-create-home app

COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

COPY . .

RUN mkdir -p /app/data \
 && chown -R app:app /app

USER app

EXPOSE 8000

# Render (and similar platforms) inject $PORT and require the app to bind to
# it; defaults to 8000 for local `docker run`/docker-compose usage. This is
# the single-process dev/small-deploy entrypoint — docker-compose.prod.yml
# overrides `command` to run Gunicorn with multiple Uvicorn workers instead.
CMD sh -c "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"
