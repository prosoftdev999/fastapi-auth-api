import uuid
from typing import IO

import boto3
from botocore.exceptions import ClientError

from app.core.config import settings


def is_storage_configured() -> bool:
    return bool(settings.s3_access_key_id and settings.s3_secret_access_key)


def get_s3_client():
    return boto3.client(
        "s3",
        endpoint_url=settings.s3_endpoint_url,
        region_name=settings.s3_region,
        aws_access_key_id=settings.s3_access_key_id,
        aws_secret_access_key=settings.s3_secret_access_key,
    )


def _ensure_bucket(client) -> None:
    try:
        client.head_bucket(Bucket=settings.s3_bucket_name)
    except ClientError:
        client.create_bucket(Bucket=settings.s3_bucket_name)


def build_object_key(user_id: int, category: str, filename: str) -> str:
    safe_name = filename.replace("/", "_").replace("\\", "_")
    return f"{category}/{user_id}/{uuid.uuid4().hex}_{safe_name}"


def upload_fileobj(
    client, fileobj: IO[bytes], key: str, content_type: str | None
) -> None:
    """Streams fileobj to S3 — boto3's upload_fileobj reads it in chunks and
    uses multipart upload for large files, never buffering the whole object
    into a single in-memory bytes value."""
    _ensure_bucket(client)
    extra_args = {"ContentType": content_type} if content_type else {}
    client.upload_fileobj(fileobj, settings.s3_bucket_name, key, ExtraArgs=extra_args)


def generate_presigned_url(client, key: str, expires_in: int = 3600) -> str:
    return client.generate_presigned_url(
        "get_object",
        Params={"Bucket": settings.s3_bucket_name, "Key": key},
        ExpiresIn=expires_in,
    )


def delete_object(client, key: str) -> None:
    client.delete_object(Bucket=settings.s3_bucket_name, Key=key)
