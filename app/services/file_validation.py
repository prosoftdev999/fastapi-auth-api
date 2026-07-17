import csv
import io
from collections.abc import Callable
from dataclasses import dataclass

from fastapi import HTTPException, UploadFile, status

from app.services.virus_scan import scan_chunk_for_viruses

CHUNK_SIZE = 1024 * 1024  # 1 MiB
_SIGNATURE_HEAD_SIZE = 32


def _looks_like_jpeg(head: bytes) -> bool:
    return head.startswith(b"\xff\xd8\xff")


def _looks_like_png(head: bytes) -> bool:
    return head.startswith(b"\x89PNG\r\n\x1a\n")


def _looks_like_gif(head: bytes) -> bool:
    return head.startswith((b"GIF87a", b"GIF89a"))


def _looks_like_webp(head: bytes) -> bool:
    return head.startswith(b"RIFF") and head[8:12] == b"WEBP"


def _looks_like_image(head: bytes) -> bool:
    return any(
        check(head)
        for check in (_looks_like_jpeg, _looks_like_png, _looks_like_gif, _looks_like_webp)
    )


def _looks_like_pdf(head: bytes) -> bool:
    return head.startswith(b"%PDF-")


def _looks_like_mp4_or_mov(head: bytes) -> bool:
    # ISO base media file format (mp4, mov, ...): a 4-byte box size followed
    # by a box type. The first box is usually "ftyp"; some encoders emit a
    # "free"/"wide" box first instead.
    return len(head) >= 8 and head[4:8] in (b"ftyp", b"free", b"wide", b"moov")


def _looks_like_webm(head: bytes) -> bool:
    return head.startswith(b"\x1a\x45\xdf\xa3")


def _looks_like_video(head: bytes) -> bool:
    return _looks_like_mp4_or_mov(head) or _looks_like_webm(head)


@dataclass(frozen=True)
class UploadCategory:
    name: str
    allowed_content_types: frozenset[str]
    max_size_bytes: int
    # None means "no reliable magic-byte check" (e.g. CSV) — validated by
    # content parsing instead, separately.
    signature_check: Callable[[bytes], bool] | None


IMAGE = UploadCategory(
    name="image",
    allowed_content_types=frozenset(
        {"image/jpeg", "image/png", "image/webp", "image/gif"}
    ),
    max_size_bytes=10 * 1024 * 1024,
    signature_check=_looks_like_image,
)

PDF = UploadCategory(
    name="pdf",
    allowed_content_types=frozenset({"application/pdf"}),
    max_size_bytes=20 * 1024 * 1024,
    signature_check=_looks_like_pdf,
)

CSV = UploadCategory(
    name="csv",
    allowed_content_types=frozenset({"text/csv", "application/vnd.ms-excel"}),
    max_size_bytes=20 * 1024 * 1024,
    signature_check=None,
)

VIDEO = UploadCategory(
    name="video",
    allowed_content_types=frozenset(
        {"video/mp4", "video/webm", "video/quicktime"}
    ),
    max_size_bytes=200 * 1024 * 1024,
    signature_check=_looks_like_video,
)

CATEGORIES: dict[str, UploadCategory] = {c.name: c for c in (IMAGE, PDF, CSV, VIDEO)}


async def read_and_validate_stream(
    upload: UploadFile, category: UploadCategory
) -> int:
    """Reads `upload` in fixed-size chunks — never holds the whole file in
    memory at once — enforcing the category's size limit, magic-byte
    signature, and virus-scan placeholder as it goes. Rewinds to the start
    on success so the caller can then stream it on to S3. Returns the total
    size in bytes.
    """
    total = 0
    head = b""

    while True:
        chunk = await upload.read(CHUNK_SIZE)
        if not chunk:
            break

        total += len(chunk)
        if total > category.max_size_bytes:
            raise HTTPException(
                status_code=status.HTTP_413_CONTENT_TOO_LARGE,
                detail=(
                    f"File exceeds the {category.max_size_bytes} byte "
                    f"limit for {category.name} uploads"
                ),
            )

        if len(head) < _SIGNATURE_HEAD_SIZE:
            head += chunk[: _SIGNATURE_HEAD_SIZE - len(head)]

        if not scan_chunk_for_viruses(chunk):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="File failed virus scan",
            )

    if total == 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Uploaded file is empty"
        )

    if category.signature_check is not None and not category.signature_check(head):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"File content does not match a valid {category.name} file",
        )

    await upload.seek(0)

    return total


async def validate_csv_content(upload: UploadFile) -> None:
    """CSV has no reliable magic bytes, so it's validated by actually
    parsing a sample instead — rejects anything that isn't valid UTF-8 text
    with at least one parsable row. Call after read_and_validate_stream
    (which already rewound the file to the start)."""
    sample = await upload.read(8192)
    await upload.seek(0)

    try:
        text = sample.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="CSV file is not valid UTF-8 text",
        ) from exc

    reader = csv.reader(io.StringIO(text))
    try:
        first_row = next(reader)
    except StopIteration as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="CSV file has no rows",
        ) from exc

    if not first_row:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="CSV file has no columns",
        )
