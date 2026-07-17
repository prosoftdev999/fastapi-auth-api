from fastapi import APIRouter, Depends, File, Form, HTTPException, Response, UploadFile, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.dependencies import get_current_user
from app.db.session import get_db
from app.models.file_upload import FileUpload
from app.models.user import User
from app.schemas.file_upload import FileDownloadResponse, FileUploadResponse
from app.schemas.pagination import Page
from app.services.file_validation import CATEGORIES, read_and_validate_stream, validate_csv_content
from app.services.pagination import (
    OffsetPaginationParams,
    apply_sort,
    get_offset_pagination,
    paginate_offset,
)
from app.services.storage import (
    build_object_key,
    delete_object,
    generate_presigned_url,
    get_s3_client,
    is_storage_configured,
    upload_fileobj,
)

router = APIRouter(prefix="/files", tags=["Files"])

_SORT_FIELDS = {"id", "created_at", "size_bytes", "filename"}


def _require_storage_configured() -> None:
    if not is_storage_configured():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="File storage is not configured",
        )


@router.post(
    "/upload",
    response_model=FileUploadResponse,
    status_code=status.HTTP_201_CREATED,
)
async def upload_file(
    category: str = Form(..., description="image | pdf | csv | video"),
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> FileUpload:
    _require_storage_configured()

    upload_category = CATEGORIES.get(category)
    if upload_category is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unknown category '{category}'. Choose one of: {sorted(CATEGORIES)}",
        )

    if file.content_type not in upload_category.allowed_content_types:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"Content-Type '{file.content_type}' is not allowed for "
                f"{category} uploads"
            ),
        )

    size_bytes = await read_and_validate_stream(file, upload_category)

    if category == "csv":
        await validate_csv_content(file)

    storage_key = build_object_key(
        current_user.id, category, file.filename or "upload"
    )

    client = get_s3_client()
    upload_fileobj(client, file.file, storage_key, content_type=file.content_type)

    record = FileUpload(
        user_id=current_user.id,
        filename=file.filename or "upload",
        content_type=file.content_type,
        category=category,
        size_bytes=size_bytes,
        storage_key=storage_key,
    )
    db.add(record)
    db.commit()
    db.refresh(record)

    return record


@router.get("/", response_model=Page[FileUploadResponse])
def list_my_files(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    pagination: OffsetPaginationParams = Depends(get_offset_pagination),
) -> Page:
    statement = select(FileUpload).where(FileUpload.user_id == current_user.id)
    statement = apply_sort(statement, FileUpload, pagination, _SORT_FIELDS)

    return paginate_offset(db, statement, pagination)


@router.get("/{file_id}", response_model=FileDownloadResponse)
def get_file(
    file_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> FileDownloadResponse:
    record = db.get(FileUpload, file_id)

    if record is None or record.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="File not found"
        )

    _require_storage_configured()

    client = get_s3_client()
    download_url = generate_presigned_url(client, record.storage_key)

    return FileDownloadResponse(
        **FileUploadResponse.model_validate(record).model_dump(),
        download_url=download_url,
    )


@router.delete("/{file_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_file(
    file_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Response:
    record = db.get(FileUpload, file_id)

    if record is None or record.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="File not found"
        )

    _require_storage_configured()

    client = get_s3_client()
    delete_object(client, record.storage_key)

    db.delete(record)
    db.commit()

    return Response(status_code=status.HTTP_204_NO_CONTENT)
