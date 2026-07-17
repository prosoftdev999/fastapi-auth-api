from pydantic import ConfigDict, field_validator

from app.schemas.user import UserResponse


class UserResponseV2(UserResponse):
    """v2 evolves GET /users/me to include what v1 needed a second request
    (GET /auth/oauth/accounts) to find out — the linked OAuth providers."""

    oauth_providers: list[str] = []

    @field_validator("oauth_providers", mode="before")
    @classmethod
    def _extract_provider_names(cls, value: object) -> object:
        if isinstance(value, list):
            return [
                item.provider if hasattr(item, "provider") else item
                for item in value
            ]
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
                    "oauth_providers": ["google"],
                }
            ]
        },
    )
