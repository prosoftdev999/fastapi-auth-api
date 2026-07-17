from fastapi.testclient import TestClient


def test_security_headers_present_on_every_response(client: TestClient) -> None:
    response = client.get("/health")

    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["x-frame-options"] == "DENY"
    assert response.headers["referrer-policy"] == "strict-origin-when-cross-origin"
    assert "permissions-policy" in response.headers


def test_hsts_is_absent_outside_production(client: TestClient) -> None:
    response = client.get("/health")

    assert "strict-transport-security" not in response.headers


def test_security_headers_present_on_error_responses(client: TestClient) -> None:
    response = client.get("/definitely-not-a-route")

    assert response.status_code == 404
    assert response.headers["x-content-type-options"] == "nosniff"
