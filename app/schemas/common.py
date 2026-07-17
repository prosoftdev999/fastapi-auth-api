from pydantic import BaseModel, ConfigDict


class MessageResponse(BaseModel):
    message: str

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [{"message": "Operation completed successfully"}]
        }
    )
