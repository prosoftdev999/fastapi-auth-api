import asyncio
import io
from unittest.mock import patch

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from moto import mock_aws

from app.auth.jwt import create_email_verification_token
from app.services.file_validation import CSV, UploadCategory, read_and_validate_stream
from app.services.virus_scan import _EICAR_SIGNATURE

USER_A = {"email": "files-user-a@example.com", "password": "SecurePass123"}
USER_B = {"email": "files-user-b@example.com", "password": "SecurePass123"}

JPEG_BYTES = b"\xff\xd8\xff\xe0" + b"\x00" * 64
PDF_BYTES = b"%PDF-1.4\n" + b"fake pdf body " * 4
CSV_BYTES = b"name,age\nAlice,30\nBob,25\n"
MP4_BYTES = b"\x00\x00\x00\x18ftypisom" + b"\x00" * 32


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


def login(client: TestClient, credentials: dict) -> str:
    response = client.post("/auth/login", json=credentials)
    assert response.status_code == 200
    return response.json()["access_token"]


def auth_headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def get_authed_client(client: TestClient) -> tuple[str, dict]:
    user = register_and_verify(client, USER_A)
    token = login(client, USER_A)
    return token, user


def test_upload_requires_authentication(client: TestClient) -> None:
    response = client.post(
        "/files/upload",
        data={"category": "image"},
        files={"file": ("photo.jpg", io.BytesIO(JPEG_BYTES), "image/jpeg")},
    )
    assert response.status_code in {401, 403}


def test_upload_rejects_unknown_category(client: TestClient) -> None:
    token, _ = get_authed_client(client)

    response = client.post(
        "/files/upload",
        data={"category": "audio"},
        files={"file": ("song.mp3", io.BytesIO(b"whatever"), "audio/mpeg")},
        headers=auth_headers(token),
    )
    assert response.status_code == 400


def test_upload_rejects_disallowed_content_type(client: TestClient) -> None:
    token, _ = get_authed_client(client)

    response = client.post(
        "/files/upload",
        data={"category": "image"},
        files={"file": ("notes.txt", io.BytesIO(b"hello"), "text/plain")},
        headers=auth_headers(token),
    )
    assert response.status_code == 400


def test_upload_rejects_content_not_matching_declared_type(
    client: TestClient,
) -> None:
    token, _ = get_authed_client(client)

    response = client.post(
        "/files/upload",
        data={"category": "image"},
        files={
            "file": (
                "fake.jpg",
                io.BytesIO(b"not actually a jpeg" * 4),
                "image/jpeg",
            )
        },
        headers=auth_headers(token),
    )
    assert response.status_code == 400
    assert "does not match" in response.json()["detail"]


def test_upload_rejects_eicar_test_signature(client: TestClient) -> None:
    token, _ = get_authed_client(client)

    response = client.post(
        "/files/upload",
        data={"category": "csv"},
        files={
            "file": (
                "infected.csv",
                io.BytesIO(_EICAR_SIGNATURE),
                "text/csv",
            )
        },
        headers=auth_headers(token),
    )
    assert response.status_code == 422
    assert "virus" in response.json()["detail"].lower()


def test_upload_rejects_invalid_csv_encoding(client: TestClient) -> None:
    token, _ = get_authed_client(client)

    response = client.post(
        "/files/upload",
        data={"category": "csv"},
        files={
            "file": (
                "bad.csv",
                io.BytesIO(b"\xff\xfe\x00invalid-utf8"),
                "text/csv",
            )
        },
        headers=auth_headers(token),
    )
    assert response.status_code == 400


def test_upload_returns_503_when_storage_not_configured(client: TestClient) -> None:
    token, _ = get_authed_client(client)

    with patch("app.api.files.is_storage_configured", return_value=False):
        response = client.post(
            "/files/upload",
            data={"category": "image"},
            files={"file": ("photo.jpg", io.BytesIO(JPEG_BYTES), "image/jpeg")},
            headers=auth_headers(token),
        )
    assert response.status_code == 503


@mock_aws
def test_upload_image_succeeds(client: TestClient) -> None:
    token, _ = get_authed_client(client)

    response = client.post(
        "/files/upload",
        data={"category": "image"},
        files={"file": ("photo.jpg", io.BytesIO(JPEG_BYTES), "image/jpeg")},
        headers=auth_headers(token),
    )

    assert response.status_code == 201
    body = response.json()
    assert body["filename"] == "photo.jpg"
    assert body["category"] == "image"
    assert body["size_bytes"] == len(JPEG_BYTES)


@mock_aws
def test_upload_pdf_succeeds(client: TestClient) -> None:
    token, _ = get_authed_client(client)

    response = client.post(
        "/files/upload",
        data={"category": "pdf"},
        files={"file": ("doc.pdf", io.BytesIO(PDF_BYTES), "application/pdf")},
        headers=auth_headers(token),
    )

    assert response.status_code == 201
    assert response.json()["category"] == "pdf"


@mock_aws
def test_upload_csv_succeeds(client: TestClient) -> None:
    token, _ = get_authed_client(client)

    response = client.post(
        "/files/upload",
        data={"category": "csv"},
        files={"file": ("data.csv", io.BytesIO(CSV_BYTES), "text/csv")},
        headers=auth_headers(token),
    )

    assert response.status_code == 201
    assert response.json()["category"] == "csv"


@mock_aws
def test_upload_video_succeeds(client: TestClient) -> None:
    token, _ = get_authed_client(client)

    response = client.post(
        "/files/upload",
        data={"category": "video"},
        files={"file": ("clip.mp4", io.BytesIO(MP4_BYTES), "video/mp4")},
        headers=auth_headers(token),
    )

    assert response.status_code == 201
    assert response.json()["category"] == "video"


@mock_aws
def test_list_my_files_only_shows_own_uploads(client: TestClient) -> None:
    token_a, _ = get_authed_client(client)
    register_and_verify(client, USER_B)
    token_b = login(client, USER_B)

    client.post(
        "/files/upload",
        data={"category": "image"},
        files={"file": ("a.jpg", io.BytesIO(JPEG_BYTES), "image/jpeg")},
        headers=auth_headers(token_a),
    )
    client.post(
        "/files/upload",
        data={"category": "image"},
        files={"file": ("b.jpg", io.BytesIO(JPEG_BYTES), "image/jpeg")},
        headers=auth_headers(token_b),
    )

    response = client.get("/files/", headers=auth_headers(token_a))
    body = response.json()

    assert body["total"] == 1
    assert body["items"][0]["filename"] == "a.jpg"


@mock_aws
def test_get_file_returns_presigned_download_url(client: TestClient) -> None:
    token, _ = get_authed_client(client)

    upload_response = client.post(
        "/files/upload",
        data={"category": "image"},
        files={"file": ("a.jpg", io.BytesIO(JPEG_BYTES), "image/jpeg")},
        headers=auth_headers(token),
    )
    file_id = upload_response.json()["id"]

    response = client.get(f"/files/{file_id}", headers=auth_headers(token))

    assert response.status_code == 200
    assert response.json()["download_url"].startswith("http")


@mock_aws
def test_get_file_404_for_another_users_file(client: TestClient) -> None:
    token_a, _ = get_authed_client(client)
    register_and_verify(client, USER_B)
    token_b = login(client, USER_B)

    upload_response = client.post(
        "/files/upload",
        data={"category": "image"},
        files={"file": ("a.jpg", io.BytesIO(JPEG_BYTES), "image/jpeg")},
        headers=auth_headers(token_a),
    )
    file_id = upload_response.json()["id"]

    response = client.get(f"/files/{file_id}", headers=auth_headers(token_b))
    assert response.status_code == 404


@mock_aws
def test_delete_file_removes_it(client: TestClient) -> None:
    token, _ = get_authed_client(client)

    upload_response = client.post(
        "/files/upload",
        data={"category": "image"},
        files={"file": ("a.jpg", io.BytesIO(JPEG_BYTES), "image/jpeg")},
        headers=auth_headers(token),
    )
    file_id = upload_response.json()["id"]

    delete_response = client.delete(f"/files/{file_id}", headers=auth_headers(token))
    assert delete_response.status_code == 204

    get_response = client.get(f"/files/{file_id}", headers=auth_headers(token))
    assert get_response.status_code == 404


def test_read_and_validate_stream_rejects_oversized_file() -> None:
    tiny_category = UploadCategory(
        name="tiny",
        allowed_content_types=frozenset({"text/csv"}),
        max_size_bytes=8,
        signature_check=None,
    )

    class FakeUpload:
        def __init__(self, data: bytes) -> None:
            self._buffer = io.BytesIO(data)

        async def read(self, size: int) -> bytes:
            return self._buffer.read(size)

        async def seek(self, offset: int) -> None:
            self._buffer.seek(offset)

    upload = FakeUpload(b"this is way more than eight bytes")

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(read_and_validate_stream(upload, tiny_category))

    assert exc_info.value.status_code == 413


def test_csv_category_has_no_signature_check() -> None:
    assert CSV.signature_check is None
