import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from starlette.websockets import WebSocketDisconnect

from app.auth.jwt import create_email_verification_token
from app.models.role import Role
from app.models.user import User
from tests.conftest import TestingSessionLocal

USER_A = {"email": "ws-user-a@example.com", "password": "SecurePass123"}
USER_B = {"email": "ws-user-b@example.com", "password": "SecurePass123"}


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


def login(client: TestClient, credentials: dict) -> dict:
    response = client.post("/auth/login", json=credentials)
    assert response.status_code == 200
    return response.json()


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


def test_websocket_rejects_missing_token(client: TestClient) -> None:
    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect("/ws"):
            pass


def test_websocket_rejects_invalid_token(client: TestClient) -> None:
    with pytest.raises(WebSocketDisconnect) as exc_info:
        with client.websocket_connect("/ws?token=not-a-real-token"):
            pass

    assert exc_info.value.code == 1008


def test_websocket_connects_with_valid_token(client: TestClient) -> None:
    register_and_verify(client, USER_A)
    tokens = login(client, USER_A)

    with client.websocket_connect(f"/ws?token={tokens['access_token']}"):
        pass


def test_websocket_private_messaging_between_two_users(client: TestClient) -> None:
    user_a = register_and_verify(client, USER_A)
    user_b = register_and_verify(client, USER_B)

    tokens_a = login(client, USER_A)
    tokens_b = login(client, USER_B)

    with client.websocket_connect(
        f"/ws?token={tokens_a['access_token']}"
    ) as ws_a:
        with client.websocket_connect(
            f"/ws?token={tokens_b['access_token']}"
        ) as ws_b:
            ws_a.send_json(
                {"type": "message", "to": user_b["id"], "body": "hello B"}
            )

            received = ws_b.receive_json()
            assert received == {
                "type": "message",
                "from": user_a["id"],
                "body": "hello B",
            }


def test_websocket_rejects_unsupported_message_type(client: TestClient) -> None:
    register_and_verify(client, USER_A)
    tokens = login(client, USER_A)

    with client.websocket_connect(f"/ws?token={tokens['access_token']}") as ws:
        ws.send_json({"type": "ping"})
        response = ws.receive_json()
        assert response["type"] == "error"


def test_websocket_rejects_malformed_message_fields(client: TestClient) -> None:
    register_and_verify(client, USER_A)
    tokens = login(client, USER_A)

    with client.websocket_connect(f"/ws?token={tokens['access_token']}") as ws:
        ws.send_json({"type": "message", "to": "not-an-int", "body": "hi"})
        response = ws.receive_json()
        assert response["type"] == "error"


def test_admin_role_assignment_notifies_connected_user(client: TestClient) -> None:
    register_and_verify(client, USER_A)
    grant_admin(USER_A["email"])
    admin_tokens = login(client, USER_A)

    target = register_and_verify(client, USER_B)
    target_tokens = login(client, USER_B)

    with client.websocket_connect(
        f"/ws?token={target_tokens['access_token']}"
    ) as target_ws:
        response = client.post(
            f"/admin/users/{target['id']}/roles",
            json={"role": "moderator"},
            headers={"Authorization": f"Bearer {admin_tokens['access_token']}"},
        )
        assert response.status_code == 200

        notification = target_ws.receive_json()
        assert notification["type"] == "notification"
        assert "moderator" in notification["body"]
