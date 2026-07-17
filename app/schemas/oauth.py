from datetime import datetime

from pydantic import BaseModel, ConfigDict


class LinkedProviderResponse(BaseModel):
    provider: str
    email: str | None
    created_at: datetime

    model_config = ConfigDict(
        from_attributes=True,
        json_schema_extra={
            "examples": [
                {
                    "provider": "google",
                    "email": "jane.doe@example.com",
                    "created_at": "2026-01-01T12:00:00Z",
                }
            ]
        },
    )
