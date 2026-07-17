from datetime import datetime

from pydantic import BaseModel, ConfigDict


class FileUploadResponse(BaseModel):
    id: int
    filename: str
    content_type: str
    category: str
    size_bytes: int
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class FileDownloadResponse(FileUploadResponse):
    download_url: str
