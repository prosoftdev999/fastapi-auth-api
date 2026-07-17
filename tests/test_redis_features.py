from fastapi.testclient import TestClient

from app.auth.jwt import create_password_reset_token

TEST_USER = {
    "email": "redis-user@example.com",
    "password": "SecurePass123",
}


def register_and_verify_user(client: TestClient) -> dict:
    registration = client.post("/auth/register", json=TEST_USER).json()

    from app.auth.jwt import create_email_verification_token

    verification_token = create_email_verification_token(
        subject=str(registration["id"])
    )
    response = client.get(
        "/auth/verify-email", params={"token": verification_token}
    )
    assert response.status_code == 200

    return registration


def login(client: TestClient) -> dict:
    response = client.post("/auth/login", json=TEST_USER)
    assert response.status_code == 200
    return response.json()


def test_logout_blacklists_access_token(client: TestClient) -> None:
    register_and_verify_user(client)
    tokens = login(client)

    logout_response = client.post(
        "/auth/logout",
        json={"refresh_token": tokens["refresh_token"]},
        headers={"Authorization": f"Bearer {tokens['access_token']}"},
    )
    assert logout_response.status_code == 204

    me_response = client.get(
        "/users/me",
        headers={"Authorization": f"Bearer {tokens['access_token']}"},
    )
    assert me_response.status_code == 401
    assert me_response.json() == {"detail": "Token has been revoked"}


def test_logout_blacklists_refresh_token(client: TestClient) -> None:
    register_and_verify_user(client)
    tokens = login(client)

    logout_response = client.post(
        "/auth/logout",
        json={"refresh_token": tokens["refresh_token"]},
        headers={"Authorization": f"Bearer {tokens['access_token']}"},
    )
    assert logout_response.status_code == 204

    refresh_response = client.post(
        "/auth/refresh",
        json={"refresh_token": tokens["refresh_token"]},
    )
    assert refresh_response.status_code == 401
    assert refresh_response.json() == {
        "detail": "Invalid or expired refresh token"
    }


def test_logout_requires_valid_access_token(client: TestClient) -> None:
    response = client.post(
        "/auth/logout",
        json={},
        headers={"Authorization": "Bearer not-a-real-token"},
    )
    assert response.status_code == 401


def test_login_is_rate_limited(client: TestClient) -> None:
    bad_credentials = {
        "email": "nobody@example.com",
        "password": "WrongPassword123",
    }

    responses = [
        client.post("/auth/login", json=bad_credentials) for _ in range(6)
    ]

    assert [r.status_code for r in responses[:5]] == [401] * 5
    assert responses[5].status_code == 429


def test_reset_password_token_is_single_use(client: TestClient) -> None:
    registration = register_and_verify_user(client)
    reset_token = create_password_reset_token(subject=str(registration["id"]))

    first_response = client.post(
        "/auth/reset-password",
        json={"token": reset_token, "new_password": "NewSecurePass456"},
    )
    assert first_response.status_code == 200

    second_response = client.post(
        "/auth/reset-password",
        json={"token": reset_token, "new_password": "AnotherPass789"},
    )
    assert second_response.status_code == 401
    assert second_response.json() == {
        "detail": "Invalid or expired password reset token"
    }
