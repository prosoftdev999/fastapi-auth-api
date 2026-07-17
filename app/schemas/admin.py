from pydantic import BaseModel, ConfigDict, EmailStr, field_validator


def _role_names(value: object) -> object:
    if isinstance(value, list):
        return [item.name if hasattr(item, "name") else item for item in value]
    return value


class AdminUserResponse(BaseModel):
    id: int
    email: EmailStr
    is_active: bool
    is_verified: bool
    roles: list[str] = []

    @field_validator("roles", mode="before")
    @classmethod
    def _extract_role_names(cls, value: object) -> object:
        return _role_names(value)

    model_config = ConfigDict(from_attributes=True)


class AdminUserUpdate(BaseModel):
    is_active: bool | None = None
    is_verified: bool | None = None

    model_config = ConfigDict(
        json_schema_extra={"examples": [{"is_active": False}]}
    )


class RoleAssignmentRequest(BaseModel):
    role: str

    model_config = ConfigDict(json_schema_extra={"examples": [{"role": "moderator"}]})


class RoleResponse(BaseModel):
    name: str
    description: str | None
    permissions: list[str] = []

    @field_validator("permissions", mode="before")
    @classmethod
    def _extract_permission_names(cls, value: object) -> object:
        return _role_names(value)

    model_config = ConfigDict(from_attributes=True)
