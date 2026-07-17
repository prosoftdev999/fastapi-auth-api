from fastapi.testclient import TestClient


def test_metrics_endpoint_exposes_prometheus_format(client: TestClient) -> None:
    response = client.get("/metrics")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/plain")
    assert "db_pool_size" in response.text
    assert "db_pool_checked_out_connections" in response.text


def test_metrics_endpoint_excluded_from_openapi_schema(client: TestClient) -> None:
    response = client.get("/openapi.json")

    assert "/metrics" not in response.json()["paths"]


def test_health_check_updates_health_gauge(client: TestClient) -> None:
    client.get("/health")

    metrics_response = client.get("/metrics")

    assert "health_check_status 1.0" in metrics_response.text


def test_request_metrics_count_instrumented_requests(client: TestClient) -> None:
    client.get("/health")

    metrics_response = client.get("/metrics")

    assert 'handler="/health"' in metrics_response.text
