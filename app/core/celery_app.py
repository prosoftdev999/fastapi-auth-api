from celery import Celery

from app.core.config import settings

celery_app = Celery(
    "fastapi_auth_api",
    broker=settings.redis_url,
    backend=settings.redis_url,
)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,
    # Workers ack only after a task finishes, and retry it elsewhere if the
    # worker dies mid-task, at the cost of possible re-execution — the right
    # tradeoff for email sending / cleanup jobs (must not silently vanish),
    # wrong for tasks that aren't safe to run twice.
    task_acks_late=True,
    worker_prefetch_multiplier=1,
)

# One periodic job today: purge stale unverified signups. Add further
# schedule entries here as more periodic tasks are introduced.
celery_app.conf.beat_schedule = {
    "cleanup-unverified-users-daily": {
        "task": "app.tasks.cleanup.cleanup_unverified_users",
        "schedule": 24 * 60 * 60,
    },
}

# Task modules register themselves with celery_app via the @celery_app.task
# decorator purely by being imported — this import is what makes that happen
# whenever celery_app is imported (by the FastAPI app, the worker, or beat).
import app.tasks  # noqa: E402,F401
