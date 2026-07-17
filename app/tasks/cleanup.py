from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from app.core.celery_app import celery_app
from app.db.session import SessionLocal
from app.models.user import User

UNVERIFIED_USER_MAX_AGE_DAYS = 7


@celery_app.task(name="app.tasks.cleanup.cleanup_unverified_users")
def cleanup_unverified_users() -> dict:
    """Scheduled daily (see celery_app.conf.beat_schedule). Removes accounts
    that registered but never verified their email within the grace period —
    otherwise they accumulate forever and permanently squat the email
    address (registration checks for an existing row by email)."""
    cutoff = datetime.now(timezone.utc) - timedelta(
        days=UNVERIFIED_USER_MAX_AGE_DAYS
    )

    db = SessionLocal()

    try:
        stale_users = list(
            db.scalars(
                select(User).where(
                    User.is_verified.is_(False),
                    User.created_at < cutoff,
                )
            )
        )

        for user in stale_users:
            db.delete(user)

        db.commit()

        return {"deleted_count": len(stale_users)}
    finally:
        db.close()
