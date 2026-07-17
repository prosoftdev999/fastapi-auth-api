from pydantic import BaseModel


class HealthCheckDetail(BaseModel):
    status: str
    error: str | None = None


class HealthResponse(BaseModel):
    status: str
    version: str
    environment: str
    checks: dict[str, HealthCheckDetail]
