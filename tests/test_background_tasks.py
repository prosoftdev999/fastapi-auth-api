from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest
from celery.exceptions import Retry
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.auth.jwt import create_email_verification_token
from app.models.role import Role
from app.models.user import User
from app.tasks.cleanup import cleanup_unverified_users
from app.tasks.email import send_verification_email_task
from tests.conftest import TestingSessionLocal

ADMIN = {"email": "tasks-admin@example.com", "password": "SecurePass123"}


def register_and_verify(client: TestClient, credentials: dict) -> dict:
    registration = client.post("/auth/register", json=credentials).json()

    verification_token = create_email_verification_token(
        subject=str(registration["id"])
    )
    response = client.get(
        "/auth/verify-email", params={"token": verification_token}
    )
    assert response.status_code == 200

    return registration


def grant_admin(email: str) -> None:
    session = TestingSessionLocal()
    try:
        user = session.scalar(select(User).where(User.email == email))
        role = session.scalar(select(Role).where(Role.name == "admin"))
        user.roles.append(role)
        session.add(user)
        session.commit()
    finally:
        session.close()


def admin_token(client: TestClient) -> str:
    register_and_verify(client, ADMIN)
    grant_admin(ADMIN["email"])
    response = client.post("/auth/login", json=ADMIN)
    assert response.status_code == 200
    return response.json()["access_token"]


def test_registration_dispatches_verification_email_task(client: TestClient) -> None:
    with patch("app.tasks.email.send_verification_email") as mock_send:
        response = client.post(
            "/auth/register",
            json={"email": "queued-user@example.com", "password": "SecurePass123"},
        )

    assert response.status_code == 201
    mock_send.assert_called_once()
    assert mock_send.call_args[0][0] == "queued-user@example.com"


def test_forgot_password_dispatches_reset_email_task(client: TestClient) -> None:
    register_and_verify(client, {"email": "reset-user@example.com", "password": "SecurePass123"})

    with patch("app.tasks.email.send_password_reset_email") as mock_send:
        response = client.post(
            "/auth/forgot-password", json={"email": "reset-user@example.com"}
        )

    assert response.status_code == 200
    mock_send.assert_called_once()


def test_email_task_retries_on_failure() -> None:
    # In eager mode, self.retry() raises celery.exceptions.Retry directly
    # rather than actually rescheduling — that's Retry being raised at all
    # (not RuntimeError leaking through unhandled) is what confirms the
    # retry path was reached instead of the task swallowing the exception.
    with (
        patch(
            "app.tasks.email.send_verification_email",
            side_effect=RuntimeError("smtp down"),
        ),
        pytest.raises(Retry),
    ):
        send_verification_email_task.apply(args=["fail@example.com", "tok"])


def test_report_endpoint_returns_computable_result(client: TestClient) -> None:
    token = admin_token(client)

    trigger_response = client.post(
        "/admin/reports/user-summary",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert trigger_response.status_code == 202
    task_id = trigger_response.json()["task_id"]

    status_response = client.get(
        f"/admin/reports/{task_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert status_response.status_code == 200

    body = status_response.json()
    assert body["status"] == "SUCCESS"
    assert body["result"]["total_users"] >= 1
    assert "admin" in body["result"]["users_by_role"]


def test_report_endpoint_requires_permission(client: TestClient) -> None:
    register_and_verify(
        client, {"email": "no-perms@example.com", "password": "SecurePass123"}
    )
    login_response = client.post(
        "/auth/login",
        json={"email": "no-perms@example.com", "password": "SecurePass123"},
    )
    token = login_response.json()["access_token"]

    response = client.post(
        "/admin/reports/user-summary",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 403


def test_cleanup_task_removes_only_stale_unverified_users(client: TestClient) -> None:
    fresh = register_and_verify(
        client, {"email": "fresh-verified@example.com", "password": "SecurePass123"}
    )

    session = TestingSessionLocal()
    try:
        stale_user = User(
            email="stale-unverified@example.com",
            hashed_password=None,
            is_active=True,
            is_verified=False,
        )
        stale_user.created_at = datetime.now(timezone.utc) - timedelta(days=10)
        session.add(stale_user)

        recent_user = User(
            email="recent-unverified@example.com",
            hashed_password=None,
            is_active=True,
            is_verified=False,
        )
        recent_user.created_at = datetime.now(timezone.utc) - timedelta(hours=1)
        session.add(recent_user)

        session.commit()
    finally:
        session.close()

    result = cleanup_unverified_users.apply()
    assert result.result == {"deleted_count": 1}

    session = TestingSessionLocal()
    try:
        remaining_emails = {
            user.email for user in session.scalars(select(User))
        }
    finally:
        session.close()

    assert "stale-unverified@example.com" not in remaining_emails
    assert "recent-unverified@example.com" in remaining_emails
    assert fresh["email"] in remaining_emails
