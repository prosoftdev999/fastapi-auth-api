from pydantic import BaseModel


class ReportTaskResponse(BaseModel):
    task_id: str
    status: str


class ReportStatusResponse(BaseModel):
    task_id: str
    status: str
    result: dict | None = None
