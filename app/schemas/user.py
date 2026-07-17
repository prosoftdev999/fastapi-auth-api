from pydantic import (
    BaseModel,
    ConfigDict,
    EmailStr,
    Field,
    field_validator,
)


def validate_password_strength(password: str) -> str:
    if not any(character.islower() for character in password):
        raise ValueError("Password must contain a lowercase letter")

    if not any(character.isupper() for character in password):
        raise ValueError("Password must contain an uppercase letter")

    if not any(character.isdigit() for character in password):
        raise ValueError("Password must contain a number")

    return password


class UserCreate(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)

    @field_validator("password")
    @classmethod
    def validate_password(cls, password: str) -> str:
        return validate_password_strength(password)

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {"email": "jane.doe@example.com", "password": "StrongPass123"}
            ]
        }
    )


class UserUpdate(BaseModel):
    email: EmailStr | None = None

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [{"email": "new.email@example.com"}]
        }
    )


class PasswordChange(BaseModel):
    current_password: str
    new_password: str = Field(min_length=8, max_length=128)

    @field_validator("new_password")
    @classmethod
    def validate_new_password(cls, password: str) -> str:
        return validate_password_strength(password)

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "current_password": "OldPass123",
                    "new_password": "NewStrongPass456",
                }
            ]
        }
    )


class UserResponse(BaseModel):
    id: int
    email: EmailStr
    is_active: bool
    is_verified: bool
    roles: list[str] = []

    @field_validator("roles", mode="before")
    @classmethod
    def _extract_role_names(cls, value: object) -> object:
        if isinstance(value, list):
            return [item.name if hasattr(item, "name") else item for item in value]
        return value

    model_config = ConfigDict(
        from_attributes=True,
        json_schema_extra={
            "examples": [
                {
                    "id": 1,
                    "email": "jane.doe@example.com",
                    "is_active": True,
                    "is_verified": True,
                    "roles": ["user"],
                }
            ]
        },
    )