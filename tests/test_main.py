from fastapi.testclient import TestClient
from sqlalchemy.exc import SQLAlchemyError

from app.db.session import get_db
from app.main import app

client = TestClient(app)


def test_root() -> None:
    response = client.get("/")

    assert response.status_code == 200
    assert response.json() == {
        "message": "FastAPI Authentication API is running",
        "status": "healthy",
    }


def test_health_check() -> None:
    response = client.get("/health")

    assert response.status_code == 200

    body = response.json()
    assert body["status"] == "ok"
    assert body["checks"]["database"] == {"status": "ok", "error": None}
    assert "version" in body
    assert "environment" in body


def test_health_check_returns_503_when_database_is_unreachable() -> None:
    class BrokenSession:
        def execute(self, *args: object, **kwargs: object) -> None:
            raise SQLAlchemyError("connection refused")

    def broken_get_db():
        yield BrokenSession()

    original_override = app.dependency_overrides[get_db]
    app.dependency_overrides[get_db] = broken_get_db

    try:
        response = client.get("/health")
    finally:
        app.dependency_overrides[get_db] = original_override

    assert response.status_code == 503

    body = response.json()
    assert body["status"] == "degraded"
    assert body["checks"]["database"]["status"] == "error"


def test_docs_available_outside_production() -> None:
    response = client.get("/openapi.json")

    assert response.status_code == 200
    schema = response.json()
    assert schema["info"]["title"] == "FastAPI Authentication API"
    tag_names = {tag["name"] for tag in schema["tags"]}
    assert {"Health", "Authentication", "Users"} <= tag_names