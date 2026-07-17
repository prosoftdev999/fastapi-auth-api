from sqlalchemy import func, select

from app.core.celery_app import celery_app
from app.db.session import SessionLocal
from app.models.role import Role
from app.models.user import User


@celery_app.task(name="app.tasks.reports.generate_user_summary_report")
def generate_user_summary_report() -> dict:
    """Runs off the request path — a real query here could take a while on
    a large table, and there's no reason to hold an HTTP connection open
    for it. Poll the result via GET /admin/reports/{task_id}."""
    db = SessionLocal()

    try:
        total_users = db.scalar(select(func.count(User.id))) or 0
        active_users = (
            db.scalar(select(func.count(User.id)).where(User.is_active.is_(True)))
            or 0
        )
        verified_users = (
            db.scalar(select(func.count(User.id)).where(User.is_verified.is_(True)))
            or 0
        )

        role_counts = dict(
            db.execute(
                select(Role.name, func.count(User.id))
                .select_from(Role)
                .join(Role.users)
                .group_by(Role.name)
            ).all()
        )

        return {
            "total_users": total_users,
            "active_users": active_users,
            "verified_users": verified_users,
            "users_by_role": role_counts,
        }
    finally:
        db.close()
