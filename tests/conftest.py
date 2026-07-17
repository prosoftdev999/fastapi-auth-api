from collections.abc import Generator
from unittest.mock import patch

import fakeredis
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.celery_app import celery_app
from app.core.config import settings
from app.core.rbac import seed_rbac_defaults
from app.core.redis_client import get_redis
from app.db.base import Base
from app.db.session import get_db
from app.main import app


# ---------------------------------------------------------------------------
# Test S3 configuration
# ---------------------------------------------------------------------------
#
# File-storage tests use Moto's mock_aws() to emulate S3.
#
# Docker Compose provides:
#     S3_ENDPOINT_URL=http://minio:9000
#
# We must explicitly clear that endpoint during tests. Otherwise boto3 tries
# to connect to the real MinIO container while using these fake test keys,
# resulting in InvalidAccessKeyId errors.
#
# With endpoint_url=None, boto3 uses the normal AWS S3 endpoint pattern,
# which Moto intercepts inside tests wrapped with mock_aws().
#
settings.s3_endpoint_url = None
settings.s3_access_key_id = "test-access-key"
settings.s3_secret_access_key = "test-secret-key"
settings.s3_bucket_name = "test-fastapi-auth-uploads"
settings.s3_region = "us-east-1"


# ---------------------------------------------------------------------------
# Celery test configuration
# ---------------------------------------------------------------------------
#
# Run Celery tasks synchronously in the same process during tests.
# No external Celery worker or broker is required.
#
celery_app.conf.task_always_eager = True
celery_app.conf.task_eager_propagates = True
celery_app.conf.task_store_eager_result = True

# Eager tests run in one process, so an in-memory result backend is sufficient.
celery_app.conf.result_backend = "cache+memory://"


# ---------------------------------------------------------------------------
# SQLite test database
# ---------------------------------------------------------------------------

TEST_DATABASE_URL = "sqlite://"

engine = create_engine(
    TEST_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)

TestingSessionLocal = sessionmaker(
    bind=engine,
    autocommit=False,
    autoflush=False,
)


def override_get_db() -> Generator:
    """Provide a fresh SQLAlchemy session for FastAPI tests."""

    db = TestingSessionLocal()

    try:
        yield db
    finally:
        db.close()


app.dependency_overrides[get_db] = override_get_db


# ---------------------------------------------------------------------------
# Fake Redis
# ---------------------------------------------------------------------------

fake_redis_client = fakeredis.FakeRedis(decode_responses=True)


def override_get_redis():
    """Return the in-memory fake Redis client."""

    return fake_redis_client


app.dependency_overrides[get_redis] = override_get_redis


# ---------------------------------------------------------------------------
# Automatic database cleanup
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def reset_database() -> Generator[None, None, None]:
    """Recreate all database tables before every test."""

    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)

    seed_session = TestingSessionLocal()

    try:
        seed_rbac_defaults(seed_session)
    finally:
        seed_session.close()

    yield

    Base.metadata.drop_all(bind=engine)


# ---------------------------------------------------------------------------
# Automatic Redis cleanup
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def reset_redis() -> Generator[None, None, None]:
    """Clear fake Redis before and after every test."""

    fake_redis_client.flushall()

    yield

    fake_redis_client.flushall()


# ---------------------------------------------------------------------------
# FastAPI test client
# ---------------------------------------------------------------------------

@pytest.fixture
def client() -> Generator[TestClient, None, None]:
    """Provide a FastAPI TestClient and close it after the test."""

    with TestClient(app) as test_client:
        yield test_client


# ---------------------------------------------------------------------------
# Mock email delivery
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def mock_email_delivery() -> Generator[None, None, None]:
    """Prevent tests from sending real verification or reset emails."""

    with (
        patch("app.tasks.email.send_verification_email"),
        patch("app.tasks.email.send_password_reset_email"),
    ):
        yield


# ---------------------------------------------------------------------------
# Override direct database sessions used by Celery tasks
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def override_task_db_session() -> Generator[None, None, None]:
    """
    Make Celery tasks use the in-memory test database.

    Celery tasks create sessions directly with SessionLocal(), so FastAPI's
    get_db dependency override does not affect them. Patch SessionLocal at
    each task module's import location.
    """

    with (
        patch("app.tasks.reports.SessionLocal", TestingSessionLocal),
        patch("app.tasks.cleanup.SessionLocal", TestingSessionLocal),
    ):
        yield