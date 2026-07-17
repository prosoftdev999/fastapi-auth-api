from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from app.schemas.user import validate_password_strength


class ForgotPasswordRequest(BaseModel):
    email: EmailStr

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [{"email": "jane.doe@example.com"}]
        }
    )


class ForgotPasswordResponse(BaseModel):
    message: str

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "message": (
                        "If an account exists for this email, password "
                        "reset instructions have been sent"
                    )
                }
            ]
        }
    )


class ResetPasswordRequest(BaseModel):
    token: str
    new_password: str = Field(
        min_length=8,
        max_length=128,
    )

    @field_validator("new_password")
    @classmethod
    def validate_new_password(cls, password: str) -> str:
        return validate_password_strength(password)

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {"token": "eyJhbGciOi...", "new_password": "NewStrongPass456"}
            ]
        }
    )