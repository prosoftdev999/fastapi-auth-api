from app.core.celery_app import celery_app
from app.services.email import send_password_reset_email, send_verification_email


@celery_app.task(
    name="app.tasks.email.send_verification_email_task",
    bind=True,
    max_retries=3,
    default_retry_delay=30,
)
def send_verification_email_task(self, recipient: str, verification_token: str) -> None:
    try:
        send_verification_email(recipient, verification_token)
    except Exception as exc:
        raise self.retry(exc=exc)


@celery_app.task(
    name="app.tasks.email.send_password_reset_email_task",
    bind=True,
    max_retries=3,
    default_retry_delay=30,
)
def send_password_reset_email_task(self, recipient: str, reset_token: str) -> None:
    try:
        send_password_reset_email(recipient, reset_token)
    except Exception as exc:
        raise self.retry(exc=exc)
