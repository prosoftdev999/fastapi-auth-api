from pydantic import BaseModel, EmailStr, Field, field_validator

from app.schemas.user import validate_password_strength


class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class ForgotPasswordResponse(BaseModel):
    message: str
    reset_token: str | None = None


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


class MessageResponse(BaseModel):
    message: str