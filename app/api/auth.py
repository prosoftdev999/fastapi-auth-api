from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.jwt import (
    create_access_token,
    create_refresh_token,
    decode_refresh_token,
)
from app.auth.password import hash_password, verify_password
from app.db.session import get_db
from app.models.user import User
from app.schemas.token import (
    AccessTokenResponse,
    LoginRequest,
    RefreshTokenRequest,
    TokenResponse,
)
from app.schemas.user import UserCreate, UserResponse

router = APIRouter(
    prefix="/auth",
    tags=["Authentication"],
)


@router.post(
    "/register",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
)
def register_user(
    user_data: UserCreate,
    db: Session = Depends(get_db),
) -> User:
    email = str(user_data.email).lower()
    existing_user = db.scalar(
        select(User).where(User.email == email)
    )

    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A user with this email already exists",
        )

    user = User(
        email=email,
        hashed_password=hash_password(user_data.password),
    )

    db.add(user)
    db.commit()
    db.refresh(user)

    return user


@router.post(
    "/login",
    response_model=TokenResponse,
)
def login_user(
    login_data: LoginRequest,
    db: Session = Depends(get_db),
) -> TokenResponse:
    email = str(login_data.email).lower()
    user = db.scalar(
        select(User).where(User.email == email)
    )

    if user is None or not verify_password(
        login_data.password,
        user.hashed_password,
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User account is inactive",
        )

    access_token = create_access_token(subject=user.email)
    refresh_token = create_refresh_token(subject=user.email)

    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        token_type="bearer",
    )

@router.post(
    "/refresh",
    response_model=AccessTokenResponse,
)
def refresh_access_token(
    token_data: RefreshTokenRequest,
    db: Session = Depends(get_db),
) -> AccessTokenResponse:
    email = decode_refresh_token(token_data.refresh_token)

    if email is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired refresh token",
        )

    user = db.scalar(
        select(User).where(User.email == email)
    )

    if user is None or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User is unavailable",
        )

    access_token = create_access_token(subject=user.email)

    return AccessTokenResponse(
        access_token=access_token,
        token_type="bearer",
    )