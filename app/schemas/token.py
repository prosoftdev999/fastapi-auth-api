from pydantic import BaseModel, ConfigDict, EmailStr

_EXAMPLE_ACCESS_TOKEN = (
    "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJqYW5lQGV4YW1wbGUuY29tIn0.signature"
)
_EXAMPLE_REFRESH_TOKEN = (
    "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJqYW5lQGV4YW1wbGUuY29tIn0.signature2"
)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {"email": "jane.doe@example.com", "password": "StrongPass123"}
            ]
        }
    )


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "access_token": _EXAMPLE_ACCESS_TOKEN,
                    "refresh_token": _EXAMPLE_REFRESH_TOKEN,
                    "token_type": "bearer",
                }
            ]
        }
    )


class LogoutRequest(BaseModel):
    refresh_token: str | None = None

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [{"refresh_token": _EXAMPLE_REFRESH_TOKEN}]
        }
    )


class RefreshTokenRequest(BaseModel):
    refresh_token: str

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [{"refresh_token": _EXAMPLE_REFRESH_TOKEN}]
        }
    )


class AccessTokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "access_token": _EXAMPLE_ACCESS_TOKEN,
                    "token_type": "bearer",
                }
            ]
        }
    )


class RegistrationResponse(BaseModel):
    id: int
    email: EmailStr
    is_active: bool
    is_verified: bool
    message: str

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "id": 1,
                    "email": "jane.doe@example.com",
                    "is_active": True,
                    "is_verified": False,
                    "message": (
                        "Registration successful. Check your email "
                        "to verify your account."
                    ),
                }
            ]
        }
    )