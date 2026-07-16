from pydantic import BaseModel, EmailStr


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class RefreshTokenRequest(BaseModel):
    refresh_token: str


class AccessTokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"

class RegistrationResponse(BaseModel):
    id: int
    email: EmailStr
    is_active: bool
    is_verified: bool
    message: str


class MessageResponse(BaseModel):
    message: str