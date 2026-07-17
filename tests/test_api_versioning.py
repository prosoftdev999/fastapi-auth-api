from fastapi.testclient import TestClient

from app.auth.jwt import create_email_verification_token

USER = {"email": "versioning-user@example.com", "password": "SecurePass123"}


def register_and_verify(client: TestClient, path_prefix: str = "") -> dict:
    registration = client.post(f"{path_prefix}/auth/register", json=USER).json()

    verification_token = create_email_verification_token(
        subject=str(registration["id"])
    )
    response = client.get(
        f"{path_prefix}/auth/verify-email", params={"token": verification_token}
    )
    assert response.status_code == 200

    return registration


def login(client: TestClient, path_prefix: str = "") -> str:
    response = client.post(f"{path_prefix}/auth/login", json=USER)
    assert response.status_code == 200
    return response.json()["access_token"]


def test_legacy_path_still_works(client: TestClient) -> None:
    response = client.post("/auth/register", json=USER)
    assert response.status_code == 201


def test_legacy_path_carries_deprecation_headers(client: TestClient) -> None:
    response = client.post("/auth/register", json=USER)

    assert response.headers["deprecation"] == "true"
    assert "sunset" in response.headers
    assert response.headers["link"] == '</api/v1/auth/register>; rel="successor-version"'


def test_v1_path_has_no_deprecation_headers(client: TestClient) -> None:
    response = client.post("/api/v1/auth/register", json=USER)

    assert response.status_code == 201
    assert "deprecation" not in response.headers


def test_v2_path_has_no_deprecation_headers(client: TestClient) -> None:
    response = client.post("/api/v2/auth/register", json=USER)

    assert response.status_code == 201
    assert "deprecation" not in response.headers


def test_infrastructure_endpoints_are_not_marked_deprecated(
    client: TestClient,
) -> None:
    for path in ("/health", "/", "/metrics", "/openapi.json"):
        response = client.get(path)
        assert "deprecation" not in response.headers, path


def test_legacy_and_v1_reach_the_same_underlying_data(client: TestClient) -> None:
    register_and_verify(client)
    token = login(client)

    legacy_response = client.get(
        "/users/me", headers={"Authorization": f"Bearer {token}"}
    )
    v1_response = client.get(
        "/api/v1/users/me", headers={"Authorization": f"Bearer {token}"}
    )

    assert legacy_response.status_code == v1_response.status_code == 200
    assert legacy_response.json() == v1_response.json()


def test_v2_users_me_includes_oauth_providers_field(client: TestClient) -> None:
    register_and_verify(client)
    token = login(client)

    response = client.get(
        "/api/v2/users/me", headers={"Authorization": f"Bearer {token}"}
    )

    assert response.status_code == 200
    body = response.json()
    assert body["oauth_providers"] == []
    assert "id" in body and "email" in body and "roles" in body


def test_v1_users_me_does_not_include_oauth_providers_field(
    client: TestClient,
) -> None:
    register_and_verify(client)
    token = login(client)

    response = client.get(
        "/api/v1/users/me", headers={"Authorization": f"Bearer {token}"}
    )

    assert response.status_code == 200
    assert "oauth_providers" not in response.json()


def test_v2_patch_users_me_still_returns_evolved_shape(client: TestClient) -> None:
    register_and_verify(client)
    token = login(client)

    response = client.patch(
        "/api/v2/users/me",
        json={"email": "new-versioning-email@example.com"},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["email"] == "new-versioning-email@example.com"
    assert "oauth_providers" in body


def test_v2_change_password_and_deactivate_behave_like_v1(
    client: TestClient,
) -> None:
    register_and_verify(client)
    token = login(client)
    headers = {"Authorization": f"Bearer {token}"}

    change_response = client.post(
        "/api/v2/users/me/change-password",
        json={
            "current_password": USER["password"],
            "new_password": "AnotherStrongPass456",
        },
        headers=headers,
    )
    assert change_response.status_code == 204

    deactivate_response = client.delete("/api/v2/users/me", headers=headers)
    assert deactivate_response.status_code == 204

    login_response = client.post("/auth/login", json=USER)
    assert login_response.status_code in {401, 403}


def test_rate_limit_is_shared_across_legacy_v1_and_v2(client: TestClient) -> None:
    # /auth/register, /api/v1/auth/register, and /api/v2/auth/register all
    # mount the exact same underlying router — they must share one rate-limit
    # bucket, not one each, or versioning would hand an attacker a 3x
    # multiplier on every per-IP limit for free.
    prefixes = ["", "/api/v1", "/api/v2", "", "/api/v1"]
    responses = [
        client.post(
            f"{prefix}/auth/register",
            json={"email": f"shared-limit-{i}@example.com", "password": "SecurePass123"},
        )
        for i, prefix in enumerate(prefixes)
    ]

    assert [r.status_code for r in responses] == [201] * 5

    sixth_response = client.post(
        "/api/v2/auth/register",
        json={"email": "shared-limit-6@example.com", "password": "SecurePass123"},
    )
    assert sixth_response.status_code == 429


def test_websocket_reachable_under_every_surface(client: TestClient) -> None:
    register_and_verify(client)
    token = login(client)

    for prefix in ("", "/api/v1", "/api/v2"):
        with client.websocket_connect(f"{prefix}/ws?token={token}"):
            pass
