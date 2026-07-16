import smtplib
from email.message import EmailMessage
from email.utils import formataddr

from app.core.config import settings


def send_email(
    recipient: str,
    subject: str,
    text_content: str,
    html_content: str,
) -> None:
    if not settings.smtp_username:
        raise RuntimeError("SMTP_USERNAME is not configured")

    if not settings.smtp_password:
        raise RuntimeError("SMTP_PASSWORD is not configured")

    sender_email = (
        settings.smtp_from_email or settings.smtp_username
    )

    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = formataddr(
        (settings.smtp_from_name, sender_email)
    )
    message["To"] = recipient

    message.set_content(text_content)
    message.add_alternative(
        html_content,
        subtype="html",
    )

    with smtplib.SMTP(
        settings.smtp_host,
        settings.smtp_port,
        timeout=15,
    ) as smtp:
        smtp.ehlo()
        smtp.starttls()
        smtp.ehlo()
        smtp.login(
            settings.smtp_username,
            settings.smtp_password,
        )
        smtp.send_message(message)


def send_verification_email(
    recipient: str,
    verification_token: str,
) -> None:
    verification_url = (
        f"{settings.frontend_url}/verify-email"
        f"?token={verification_token}"
    )

    subject = "Verify your email address"

    text_content = (
        "Welcome to FastAPI Authentication API.\n\n"
        "Verify your email by opening this link:\n"
        f"{verification_url}\n\n"
        "This link expires in 30 minutes."
    )

    html_content = f"""
    <!DOCTYPE html>
    <html lang="en">
      <body style="font-family: Arial, sans-serif;">
        <h2>Verify your email address</h2>

        <p>
          Welcome to FastAPI Authentication API.
        </p>

        <p>
          Click the button below to verify your email.
        </p>

        <p>
          <a
            href="{verification_url}"
            style="
              display: inline-block;
              padding: 12px 20px;
              background: #111827;
              color: #ffffff;
              text-decoration: none;
              border-radius: 6px;
            "
          >
            Verify email
          </a>
        </p>

        <p>
          This link expires in 30 minutes.
        </p>

        <p>
          If the button does not work, open:
        </p>

        <p>{verification_url}</p>
      </body>
    </html>
    """

    send_email(
        recipient=recipient,
        subject=subject,
        text_content=text_content,
        html_content=html_content,
    )


def send_password_reset_email(
    recipient: str,
    reset_token: str,
) -> None:
    reset_url = (
        f"{settings.frontend_url}/reset-password"
        f"?token={reset_token}"
    )

    subject = "Reset your password"

    text_content = (
        "A password-reset request was received.\n\n"
        "Reset your password by opening this link:\n"
        f"{reset_url}\n\n"
        "This link expires in 15 minutes.\n\n"
        "Ignore this message if you did not request it."
    )

    html_content = f"""
    <!DOCTYPE html>
    <html lang="en">
      <body style="font-family: Arial, sans-serif;">
        <h2>Reset your password</h2>

        <p>
          A password-reset request was received for your account.
        </p>

        <p>
          Click the button below to select a new password.
        </p>

        <p>
          <a
            href="{reset_url}"
            style="
              display: inline-block;
              padding: 12px 20px;
              background: #111827;
              color: #ffffff;
              text-decoration: none;
              border-radius: 6px;
            "
          >
            Reset password
          </a>
        </p>

        <p>
          This link expires in 15 minutes.
        </p>

        <p>
          Ignore this email if you did not request a password reset.
        </p>

        <p>
          If the button does not work, open:
        </p>

        <p>{reset_url}</p>
      </body>
    </html>
    """

    send_email(
        recipient=recipient,
        subject=subject,
        text_content=text_content,
        html_content=html_content,
    )