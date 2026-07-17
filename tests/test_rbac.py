from fastapi.testclient import TestClient
from sqlalchemy import select

from app.auth.jwt import create_email_verification_token
from app.models.role import Role
from app.models.user import User
from tests.conftest import TestingSessionLocal

USER_A = {"email": "rbac-user-a@example.com", "password": "SecurePass123"}
USER_B = {"email": "rbac-user-b@example.com", "password": "SecurePass123"}


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


def login(client: TestClient, credentials: dict) -> str:
    response = client.post("/auth/login", json=credentials)
    assert response.status_code == 200
    return response.json()["access_token"]


def grant_role(email: str, role_name: str) -> None:
    session = TestingSessionLocal()
    try:
        user = session.scalar(select(User).where(User.email == email))
        role = session.scalar(select(Role).where(Role.name == role_name))
        user.roles.append(role)
        session.add(user)
        session.commit()
    finally:
        session.close()


def auth_headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_regular_user_cannot_list_admin_users(client: TestClient) -> None:
    register_and_verify(client, USER_A)
    token = login(client, USER_A)

    response = client.get("/admin/users", headers=auth_headers(token))

    assert response.status_code == 403
    assert response.json() == {
        "detail": "You do not have the required permission for this action"
    }


def test_admin_can_list_users(client: TestClient) -> None:
    register_and_verify(client, USER_A)
    grant_role(USER_A["email"], "admin")
    token = login(client, USER_A)

    response = client.get("/admin/users", headers=auth_headers(token))

    assert response.status_code == 200
    body = response.json()
    emails = {user["email"] for user in body["items"]}
    assert USER_A["email"] in emails
    assert body["total"] >= 1


def test_admin_can_update_user_status(client: TestClient) -> None:
    register_and_verify(client, USER_A)
    grant_role(USER_A["email"], "admin")
    admin_token = login(client, USER_A)

    target = register_and_verify(client, USER_B)

    response = client.patch(
        f"/admin/users/{target['id']}",
        json={"is_active": False},
        headers=auth_headers(admin_token),
    )

    assert response.status_code == 200
    assert response.json()["is_active"] is False

    login_response = client.post("/auth/login", json=USER_B)
    assert login_response.status_code in {401, 403}


def test_moderator_can_read_but_not_delete(client: TestClient) -> None:
    register_and_verify(client, USER_A)
    grant_role(USER_A["email"], "moderator")
    moderator_token = login(client, USER_A)

    target = register_and_verify(client, USER_B)

    list_response = client.get(
        "/admin/users", headers=auth_headers(moderator_token)
    )
    assert list_response.status_code == 200

    delete_response = client.delete(
        f"/admin/users/{target['id']}", headers=auth_headers(moderator_token)
    )
    assert delete_response.status_code == 403


def test_admin_can_deactivate_user(client: TestClient) -> None:
    register_and_verify(client, USER_A)
    grant_role(USER_A["email"], "admin")
    admin_token = login(client, USER_A)

    target = register_and_verify(client, USER_B)

    response = client.delete(
        f"/admin/users/{target['id']}", headers=auth_headers(admin_token)
    )
    assert response.status_code == 204

    login_response = client.post("/auth/login", json=USER_B)
    assert login_response.status_code in {401, 403}


def test_admin_can_assign_and_revoke_role(client: TestClient) -> None:
    register_and_verify(client, USER_A)
    grant_role(USER_A["email"], "admin")
    admin_token = login(client, USER_A)

    target = register_and_verify(client, USER_B)

    assign_response = client.post(
        f"/admin/users/{target['id']}/roles",
        json={"role": "moderator"},
        headers=auth_headers(admin_token),
    )
    assert assign_response.status_code == 200
    assert set(assign_response.json()["roles"]) == {"user", "moderator"}

    revoke_response = client.delete(
        f"/admin/users/{target['id']}/roles/moderator",
        headers=auth_headers(admin_token),
    )
    assert revoke_response.status_code == 200
    assert set(revoke_response.json()["roles"]) == {"user"}


def test_admin_assign_unknown_role_returns_404(client: TestClient) -> None:
    register_and_verify(client, USER_A)
    grant_role(USER_A["email"], "admin")
    admin_token = login(client, USER_A)

    target = register_and_verify(client, USER_B)

    response = client.post(
        f"/admin/users/{target['id']}/roles",
        json={"role": "superuser"},
        headers=auth_headers(admin_token),
    )
    assert response.status_code == 404


def test_admin_routes_require_authentication(client: TestClient) -> None:
    response = client.get("/admin/users")
    assert response.status_code in {401, 403}
