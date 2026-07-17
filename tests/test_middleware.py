import uuid

from fastapi.testclient import TestClient


def test_response_includes_request_id_header(client: TestClient) -> None:
    response = client.get("/health")

    assert "x-request-id" in response.headers
    uuid.UUID(response.headers["x-request-id"])


def test_incoming_request_id_is_propagated(client: TestClient) -> None:
    custom_id = str(uuid.uuid4())

    response = client.get("/health", headers={"X-Request-ID": custom_id})

    assert response.headers["x-request-id"] == custom_id


def test_request_ids_are_unique_when_not_supplied(client: TestClient) -> None:
    first = client.get("/health").headers["x-request-id"]
    second = client.get("/health").headers["x-request-id"]

    assert first != second


def test_gzip_middleware_is_active(client: TestClient) -> None:
    response = client.get(
        "/health", headers={"Accept-Encoding": "gzip"}
    )

    assert response.status_code == 200
