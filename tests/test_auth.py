from fastapi.testclient import TestClient


TEST_USER = {
    "email": "developer@example.com",
    "password": "SecurePass123",
}


def register_user(client: TestClient) -> dict:
    response = client.post("/auth/register", json=TEST_USER)

    assert response.status_code == 201

    return response.json()


def register_and_verify_user(client: TestClient) -> dict:
    registration = register_user(client)

    verification_token = registration["verification_token"]

    response = client.get(
        "/auth/verify-email",
        params={"token": verification_token},
    )

    assert response.status_code == 200

    return registration


def login_user(client: TestClient) -> dict:
    response = client.post("/auth/login", json=TEST_USER)

    assert response.status_code == 200

    body = response.json()

    assert body["token_type"] == "bearer"
    assert isinstance(body["access_token"], str)
    assert isinstance(body["refresh_token"], str)

    return body


def get_access_token(client: TestClient) -> str:
    return login_user(client)["access_token"]


def auth_headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_register_user(client: TestClient) -> None:
    body = register_user(client)

    assert body["id"] == 1
    assert body["email"] == TEST_USER["email"]
    assert body["is_active"] is True
    assert body["is_verified"] is False
    assert isinstance(body["verification_token"], str)


def test_duplicate_registration(client: TestClient) -> None:
    register_user(client)

    response = client.post("/auth/register", json=TEST_USER)

    assert response.status_code == 409
    assert response.json() == {
        "detail": "A user with this email already exists"
    }


def test_login_rejected_before_email_verification(
    client: TestClient,
) -> None:
    register_user(client)

    response = client.post("/auth/login", json=TEST_USER)

    assert response.status_code == 403
    assert response.json() == {
        "detail": "Email address is not verified"
    }


def test_verify_email(client: TestClient) -> None:
    registration = register_user(client)

    response = client.get(
        "/auth/verify-email",
        params={"token": registration["verification_token"]},
    )

    assert response.status_code == 200
    assert response.json() == {
        "message": "Email verified successfully"
    }


def test_verify_email_rejects_invalid_token(
    client: TestClient,
) -> None:
    response = client.get(
        "/auth/verify-email",
        params={"token": "invalid-token"},
    )

    assert response.status_code == 401
    assert response.json() == {
        "detail": "Invalid or expired verification token"
    }


def test_login_returns_tokens(client: TestClient) -> None:
    register_and_verify_user(client)

    body = login_user(client)

    assert body["access_token"]
    assert body["refresh_token"]


def test_login_with_wrong_password(client: TestClient) -> None:
    register_and_verify_user(client)

    response = client.post(
        "/auth/login",
        json={
            "email": TEST_USER["email"],
            "password": "WrongPassword123",
        },
    )

    assert response.status_code == 401
    assert response.json() == {
        "detail": "Invalid email or password"
    }


def test_read_current_user(client: TestClient) -> None:
    register_and_verify_user(client)
    token = get_access_token(client)

    response = client.get(
        "/users/me",
        headers=auth_headers(token),
    )

    assert response.status_code == 200
    assert response.json() == {
        "id": 1,
        "email": TEST_USER["email"],
        "is_active": True,
        "is_verified": True,
    }


def test_read_current_user_without_token(
    client: TestClient,
) -> None:
    response = client.get("/users/me")

    assert response.status_code in {401, 403}


def test_refresh_returns_new_access_token(
    client: TestClient,
) -> None:
    register_and_verify_user(client)

    login_response = client.post(
        "/auth/login",
        json=TEST_USER,
    )

    assert login_response.status_code == 200

    refresh_token = login_response.json()["refresh_token"]

    response = client.post(
        "/auth/refresh",
        json={"refresh_token": refresh_token},
    )

    assert response.status_code == 200

    body = response.json()

    assert body["token_type"] == "bearer"
    assert isinstance(body["access_token"], str)
    assert "refresh_token" not in body


def test_refresh_rejects_access_token(
    client: TestClient,
) -> None:
    register_and_verify_user(client)

    login_response = client.post(
        "/auth/login",
        json=TEST_USER,
    )

    assert login_response.status_code == 200

    access_token = login_response.json()["access_token"]

    response = client.post(
        "/auth/refresh",
        json={"refresh_token": access_token},
    )

    assert response.status_code == 401
    assert response.json() == {
        "detail": "Invalid or expired refresh token"
    }


def test_refresh_rejects_invalid_token(
    client: TestClient,
) -> None:
    response = client.post(
        "/auth/refresh",
        json={"refresh_token": "not-a-valid-jwt"},
    )

    assert response.status_code == 401
    assert response.json() == {
        "detail": "Invalid or expired refresh token"
    }


def test_update_current_user_email(
    client: TestClient,
) -> None:
    register_and_verify_user(client)
    token = get_access_token(client)

    response = client.patch(
        "/users/me",
        json={"email": "updated@example.com"},
        headers=auth_headers(token),
    )

    assert response.status_code == 200
    assert response.json() == {
        "id": 1,
        "email": "updated@example.com",
        "is_active": True,
        "is_verified": True,
    }


def test_change_password(client: TestClient) -> None:
    register_and_verify_user(client)
    token = get_access_token(client)

    response = client.post(
        "/users/me/change-password",
        json={
            "current_password": TEST_USER["password"],
            "new_password": "NewSecurePass456",
        },
        headers=auth_headers(token),
    )

    assert response.status_code == 204

    old_login = client.post("/auth/login", json=TEST_USER)
    assert old_login.status_code == 401

    new_login = client.post(
        "/auth/login",
        json={
            "email": TEST_USER["email"],
            "password": "NewSecurePass456",
        },
    )

    assert new_login.status_code == 200


def test_change_password_rejects_wrong_current_password(
    client: TestClient,
) -> None:
    register_and_verify_user(client)
    token = get_access_token(client)

    response = client.post(
        "/users/me/change-password",
        json={
            "current_password": "WrongPassword123",
            "new_password": "NewSecurePass456",
        },
        headers=auth_headers(token),
    )

    assert response.status_code == 400
    assert response.json() == {
        "detail": "Current password is incorrect"
    }


def test_deactivate_current_user(
    client: TestClient,
) -> None:
    register_and_verify_user(client)
    token = get_access_token(client)

    response = client.delete(
        "/users/me",
        headers=auth_headers(token),
    )

    assert response.status_code == 204

    login_response = client.post(
        "/auth/login",
        json=TEST_USER,
    )

    assert login_response.status_code in {401, 403}


def test_forgot_password_returns_reset_token(
    client: TestClient,
) -> None:
    register_and_verify_user(client)

    response = client.post(
        "/auth/forgot-password",
        json={"email": TEST_USER["email"]},
    )

    assert response.status_code == 200

    body = response.json()

    assert "message" in body
    assert isinstance(body["reset_token"], str)


def test_forgot_password_hides_unknown_email(
    client: TestClient,
) -> None:
    response = client.post(
        "/auth/forgot-password",
        json={"email": "missing@example.com"},
    )

    assert response.status_code == 200

    body = response.json()

    assert "message" in body
    assert body["reset_token"] is None


def test_reset_password(client: TestClient) -> None:
    register_and_verify_user(client)

    forgot_response = client.post(
        "/auth/forgot-password",
        json={"email": TEST_USER["email"]},
    )

    assert forgot_response.status_code == 200

    reset_token = forgot_response.json()["reset_token"]

    reset_response = client.post(
        "/auth/reset-password",
        json={
            "token": reset_token,
            "new_password": "NewSecurePass456",
        },
    )

    assert reset_response.status_code == 200
    assert reset_response.json() == {
        "message": "Password reset successfully"
    }

    old_login = client.post(
        "/auth/login",
        json=TEST_USER,
    )

    assert old_login.status_code == 401

    new_login = client.post(
        "/auth/login",
        json={
            "email": TEST_USER["email"],
            "password": "NewSecurePass456",
        },
    )

    assert new_login.status_code == 200


def test_reset_password_rejects_invalid_token(
    client: TestClient,
) -> None:
    response = client.post(
        "/auth/reset-password",
        json={
            "token": "invalid-token",
            "new_password": "NewSecurePass456",
        },
    )

    assert response.status_code == 401
    assert response.json() == {
        "detail": "Invalid or expired password reset token"
    }


def test_reset_password_rejects_same_password(
    client: TestClient,
) -> None:
    register_and_verify_user(client)

    forgot_response = client.post(
        "/auth/forgot-password",
        json={"email": TEST_USER["email"]},
    )

    assert forgot_response.status_code == 200

    reset_token = forgot_response.json()["reset_token"]

    response = client.post(
        "/auth/reset-password",
        json={
            "token": reset_token,
            "new_password": TEST_USER["password"],
        },
    )

    assert response.status_code == 400
    assert response.json() == {
        "detail": "New password must be different"
    }