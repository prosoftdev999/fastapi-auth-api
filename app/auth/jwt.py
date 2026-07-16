from datetime import datetime, timedelta, timezone
from typing import Any

from jose import JWTError, jwt

from app.core.config import settings

ALGORITHM = "HS256"


def create_token(
    subject: str,
    token_type: str,
    expires_delta: timedelta,
) -> str:
    now = datetime.now(timezone.utc)

    payload = {
        "sub": subject,
        "type": token_type,
        "iat": now,
        "exp": now + expires_delta,
    }

    return jwt.encode(
        payload,
        settings.secret_key,
        algorithm=ALGORITHM,
    )


def create_access_token(subject: str) -> str:
    return create_token(
        subject=subject,
        token_type="access",
        expires_delta=timedelta(
            minutes=settings.access_token_expire_minutes
        ),
    )


def create_refresh_token(subject: str) -> str:
    return create_token(
        subject=subject,
        token_type="refresh",
        expires_delta=timedelta(
            days=settings.refresh_token_expire_days
        ),
    )


def decode_token(token: str, expected_type: str) -> str | None:
    try:
        payload: dict[str, Any] = jwt.decode(
            token,
            settings.secret_key,
            algorithms=[ALGORITHM],
        )

        subject = payload.get("sub")
        token_type = payload.get("type")

        if not isinstance(subject, str):
            return None

        if token_type != expected_type:
            return None

        return subject

    except JWTError:
        return None


def decode_access_token(token: str) -> str | None:
    return decode_token(token, expected_type="access")


def decode_refresh_token(token: str) -> str | None:
    return decode_token(token, expected_type="refresh")

def create_email_verification_token(subject: str) -> str:
    return create_token(
        subject=subject,
        token_type="email_verification",
        expires_delta=timedelta(minutes=30),
    )


def decode_email_verification_token(token: str) -> str | None:
    return decode_token(
        token,
        expected_type="email_verification",
    )

def create_password_reset_token(subject: str) -> str:
    return create_token(
        subject=subject,
        token_type="password_reset",
        expires_delta=timedelta(minutes=15),
    )


def decode_password_reset_token(token: str) -> str | None:
    return decode_token(
        token,
        expected_type="password_reset",
    )