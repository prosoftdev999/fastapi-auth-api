from fastapi.testclient import TestClient
from sqlalchemy import select

from app.auth.jwt import create_email_verification_token
from app.auth.password import hash_password
from app.models.role import Role
from app.models.user import User
from tests.conftest import TestingSessionLocal

ADMIN = {"email": "pagination-admin@example.com", "password": "SecurePass123"}


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


def auth_headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def seed_users(client: TestClient, count: int) -> list[dict]:
    # Inserted directly via the DB rather than POST /auth/register: bulk
    # registration would otherwise trip the per-IP rate limiter, which these
    # pagination tests aren't exercising.
    session = TestingSessionLocal()
    try:
        user_role = session.scalar(select(Role).where(Role.name == "user"))
        created = []

        for i in range(count):
            email = f"pagination-user-{i}@example.com"
            user = User(
                email=email,
                hashed_password=hash_password("SecurePass123"),
                is_active=True,
                is_verified=True,
            )
            user.roles.append(user_role)
            session.add(user)
            session.flush()
            created.append({"id": user.id, "email": user.email})

        session.commit()
        return created
    finally:
        session.close()


def test_offset_pagination_reports_total_and_has_more(client: TestClient) -> None:
    token = admin_token(client)
    seed_users(client, 5)  # + 1 admin = 6 users total

    first_page = client.get(
        "/admin/users?limit=2&offset=0", headers=auth_headers(token)
    ).json()
    assert len(first_page["items"]) == 2
    assert first_page["total"] == 6
    assert first_page["has_more"] is True

    last_page = client.get(
        "/admin/users?limit=2&offset=4", headers=auth_headers(token)
    ).json()
    assert len(last_page["items"]) == 2
    assert last_page["has_more"] is False


def test_offset_pagination_rejects_limit_above_max(client: TestClient) -> None:
    token = admin_token(client)

    response = client.get(
        "/admin/users?limit=1000", headers=auth_headers(token)
    )
    assert response.status_code == 422


def test_offset_pagination_sorts_by_requested_field(client: TestClient) -> None:
    token = admin_token(client)
    seed_users(client, 3)

    response = client.get(
        "/admin/users?sort=email&order=desc&limit=100",
        headers=auth_headers(token),
    )
    emails = [item["email"] for item in response.json()["items"]]
    assert emails == sorted(emails, reverse=True)


def test_offset_pagination_filters_by_is_active(client: TestClient) -> None:
    token = admin_token(client)
    users = seed_users(client, 2)

    client.patch(
        f"/admin/users/{users[0]['id']}",
        json={"is_active": False},
        headers=auth_headers(token),
    )

    response = client.get(
        "/admin/users?is_active=false&limit=100", headers=auth_headers(token)
    )
    body = response.json()
    assert all(item["is_active"] is False for item in body["items"])
    assert any(item["id"] == users[0]["id"] for item in body["items"])


def test_offset_pagination_searches_by_email(client: TestClient) -> None:
    token = admin_token(client)
    seed_users(client, 3)

    response = client.get(
        "/admin/users?q=pagination-user-1", headers=auth_headers(token)
    )
    body = response.json()
    assert len(body["items"]) == 1
    assert "pagination-user-1" in body["items"][0]["email"]


def test_cursor_pagination_walks_through_all_users_without_duplicates(
    client: TestClient,
) -> None:
    token = admin_token(client)
    seed_users(client, 5)  # + 1 admin = 6 users total

    seen_ids: set[int] = set()
    cursor: str | None = None

    for _ in range(10):  # safety bound against infinite loop on a bug
        query = f"?limit=2&cursor={cursor}" if cursor else "?limit=2"
        response = client.get(f"/admin/users/feed{query}", headers=auth_headers(token))
        assert response.status_code == 200

        body = response.json()
        for item in body["items"]:
            assert item["id"] not in seen_ids
            seen_ids.add(item["id"])

        if not body["has_more"]:
            assert body["next_cursor"] is None
            break

        cursor = body["next_cursor"]
    else:
        raise AssertionError("cursor pagination did not terminate")

    assert len(seen_ids) == 6


def test_cursor_pagination_rejects_invalid_cursor(client: TestClient) -> None:
    token = admin_token(client)

    response = client.get(
        "/admin/users/feed?cursor=not-valid-base64!!!",
        headers=auth_headers(token),
    )
    assert response.status_code == 400
