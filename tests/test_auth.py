from fastapi.testclient import TestClient


TEST_USER = {
    "email": "developer@example.com",
    "password": "SecurePass123",
}


def register_user(client: TestClient) -> None:
    response = client.post("/auth/register", json=TEST_USER)
    assert response.status_code == 201


def login_user(client: TestClient) -> str:
    response = client.post("/auth/login", json=TEST_USER)

    assert response.status_code == 200

    body = response.json()

    assert body["token_type"] == "bearer"
    assert isinstance(body["access_token"], str)
    assert isinstance(body["refresh_token"], str)

    return body["access_token"]


def test_register_user(client: TestClient) -> None:
    response = client.post("/auth/register", json=TEST_USER)

    assert response.status_code == 201
    assert response.json() == {
        "id": 1,
        "email": TEST_USER["email"],
        "is_active": True,
    }


def test_duplicate_registration(client: TestClient) -> None:
    register_user(client)

    response = client.post("/auth/register", json=TEST_USER)

    assert response.status_code == 409
    assert response.json() == {
        "detail": "A user with this email already exists"
    }


def test_login_returns_tokens(client: TestClient) -> None:
    register_user(client)

    response = client.post("/auth/login", json=TEST_USER)

    assert response.status_code == 200

    body = response.json()

    assert body["token_type"] == "bearer"
    assert isinstance(body["access_token"], str)
    assert isinstance(body["refresh_token"], str)


def test_login_with_wrong_password(client: TestClient) -> None:
    register_user(client)

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
    register_user(client)
    access_token = login_user(client)

    response = client.get(
        "/users/me",
        headers={"Authorization": f"Bearer {access_token}"},
    )

    assert response.status_code == 200
    assert response.json() == {
        "id": 1,
        "email": TEST_USER["email"],
        "is_active": True,
    }


def test_read_current_user_without_token(client: TestClient) -> None:
    response = client.get("/users/me")

    assert response.status_code in {401, 403}


def test_refresh_returns_new_access_token(
    client: TestClient,
) -> None:
    register_user(client)

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
    register_user(client)

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