import urllib.parse
from unittest.mock import patch

from fastapi.testclient import TestClient

TEST_USER = {
    "email": "oauth-base-user@example.com",
    "password": "SecurePass123",
}


class FakeOAuthClient:
    def __init__(self, provider_user_id: str, email: str | None) -> None:
        self.provider_user_id = provider_user_id
        self.email = email

    async def create_authorization_url(self, redirect_uri: str, state: str) -> str:
        return f"https://fake-provider.example/authorize?state={state}"

    async def fetch_access_token(self, redirect_uri: str, code: str) -> dict:
        return {"access_token": "fake-provider-token"}

    async def fetch_identity(self, token: dict) -> tuple[str, str | None]:
        return self.provider_user_id, self.email


def extract_state(redirect_response) -> str:
    parsed = urllib.parse.urlparse(redirect_response.headers["location"])
    return urllib.parse.parse_qs(parsed.query)["state"][0]


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


def test_oauth_login_redirects_to_provider(client: TestClient) -> None:
    fake_client = FakeOAuthClient("google-uid-1", "new-oauth-user@example.com")

    with patch("app.api.oauth.get_oauth_client", return_value=fake_client):
        response = client.get("/auth/oauth/google/login", follow_redirects=False)

    assert response.status_code in (302, 307)
    assert "fake-provider.example" in response.headers["location"]


def test_oauth_unknown_provider_returns_404(client: TestClient) -> None:
    response = client.get("/auth/oauth/not-a-provider/login", follow_redirects=False)
    assert response.status_code == 404


def test_oauth_unconfigured_provider_returns_503(client: TestClient) -> None:
    # No monkeypatch here: the real registry has no credentials configured
    # for any provider in the test environment.
    response = client.get("/auth/oauth/google/login", follow_redirects=False)
    assert response.status_code == 503


def test_oauth_callback_creates_new_user_and_returns_tokens(
    client: TestClient,
) -> None:
    fake_client = FakeOAuthClient("google-uid-2", "brand-new@example.com")

    with patch("app.api.oauth.get_oauth_client", return_value=fake_client):
        login_response = client.get(
            "/auth/oauth/google/login", follow_redirects=False
        )
        state = extract_state(login_response)

        callback_response = client.get(
            "/auth/oauth/google/callback",
            params={"code": "fake-code", "state": state},
        )

    assert callback_response.status_code == 200
    body = callback_response.json()
    assert body["token_type"] == "bearer"
    assert isinstance(body["access_token"], str)

    me_response = client.get(
        "/users/me",
        headers={"Authorization": f"Bearer {body['access_token']}"},
    )
    assert me_response.status_code == 200
    assert me_response.json()["email"] == "brand-new@example.com"


def test_oauth_callback_reuses_existing_linked_account(client: TestClient) -> None:
    fake_client = FakeOAuthClient("google-uid-3", "repeat-user@example.com")

    with patch("app.api.oauth.get_oauth_client", return_value=fake_client):
        for _ in range(2):
            login_response = client.get(
                "/auth/oauth/google/login", follow_redirects=False
            )
            state = extract_state(login_response)
            callback_response = client.get(
                "/auth/oauth/google/callback",
                params={"code": "fake-code", "state": state},
            )
            assert callback_response.status_code == 200

        accounts_response = client.get(
            "/auth/oauth/accounts",
            headers={
                "Authorization": f"Bearer {callback_response.json()['access_token']}"
            },
        )

    assert accounts_response.status_code == 200
    assert len(accounts_response.json()) == 1


def test_oauth_callback_rejects_invalid_state(client: TestClient) -> None:
    fake_client = FakeOAuthClient("google-uid-4", "someone@example.com")

    with patch("app.api.oauth.get_oauth_client", return_value=fake_client):
        response = client.get(
            "/auth/oauth/google/callback",
            params={"code": "fake-code", "state": "not-a-real-state"},
        )

    assert response.status_code == 400


def test_oauth_link_attaches_provider_to_existing_user(client: TestClient) -> None:
    register_and_verify_user(client)
    login_response = client.post("/auth/login", json=TEST_USER)
    access_token = login_response.json()["access_token"]

    fake_client = FakeOAuthClient("github-uid-1", "different-email@example.com")

    with patch("app.api.oauth.get_oauth_client", return_value=fake_client):
        link_start = client.get(
            "/auth/oauth/github/link",
            headers={"Authorization": f"Bearer {access_token}"},
            follow_redirects=False,
        )
        state = extract_state(link_start)

        callback_response = client.get(
            "/auth/oauth/github/callback",
            params={"code": "fake-code", "state": state},
        )
        assert callback_response.status_code == 200

        accounts_response = client.get(
            "/auth/oauth/accounts",
            headers={"Authorization": f"Bearer {access_token}"},
        )

    assert accounts_response.status_code == 200
    providers = {item["provider"] for item in accounts_response.json()}
    assert providers == {"github"}


def test_oauth_unlink_removes_linked_provider(client: TestClient) -> None:
    register_and_verify_user(client)
    login_response = client.post("/auth/login", json=TEST_USER)
    access_token = login_response.json()["access_token"]

    fake_client = FakeOAuthClient("github-uid-2", "linked@example.com")

    with patch("app.api.oauth.get_oauth_client", return_value=fake_client):
        link_start = client.get(
            "/auth/oauth/github/link",
            headers={"Authorization": f"Bearer {access_token}"},
            follow_redirects=False,
        )
        state = extract_state(link_start)
        client.get(
            "/auth/oauth/github/callback",
            params={"code": "fake-code", "state": state},
        )

    unlink_response = client.delete(
        "/auth/oauth/github",
        headers={"Authorization": f"Bearer {access_token}"},
    )
    assert unlink_response.status_code == 204

    accounts_response = client.get(
        "/auth/oauth/accounts",
        headers={"Authorization": f"Bearer {access_token}"},
    )
    assert accounts_response.json() == []


def test_oauth_cannot_unlink_only_sign_in_method(client: TestClient) -> None:
    fake_client = FakeOAuthClient("google-uid-5", "oauth-only@example.com")

    with patch("app.api.oauth.get_oauth_client", return_value=fake_client):
        login_response = client.get(
            "/auth/oauth/google/login", follow_redirects=False
        )
        state = extract_state(login_response)
        callback_response = client.get(
            "/auth/oauth/google/callback",
            params={"code": "fake-code", "state": state},
        )

    access_token = callback_response.json()["access_token"]

    unlink_response = client.delete(
        "/auth/oauth/google",
        headers={"Authorization": f"Bearer {access_token}"},
    )
    assert unlink_response.status_code == 400
