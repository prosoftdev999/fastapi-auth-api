from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Response,
    status,
)
from fastapi.security import HTTPAuthorizationCredentials
from redis import Redis
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.dependencies import bearer_scheme
from app.auth.jwt import (
    create_access_token,
    create_email_verification_token,
    create_password_reset_token,
    create_refresh_token,
    decode_access_token,
    decode_email_verification_token,
    decode_password_reset_token,
    decode_refresh_token,
    remaining_ttl_seconds,
)
from app.auth.password import hash_password, verify_password
from app.core.rbac import DEFAULT_USER_ROLE_NAME
from app.core.redis_client import get_redis
from app.db.session import get_db
from app.models.role import Role
from app.models.user import User
from app.schemas.common import MessageResponse
from app.schemas.token import (
    AccessTokenResponse,
    LoginRequest,
    LogoutRequest,
    RefreshTokenRequest,
    RegistrationResponse,
    TokenResponse,
)
from app.schemas.password_reset import (
    ForgotPasswordRequest,
    ForgotPasswordResponse,
    ResetPasswordRequest,
)
from app.schemas.user import UserCreate, UserResponse
from app.services.rate_limit import RateLimiter
from app.services.token_blacklist import (
    blacklist_token,
    is_token_blacklisted,
    is_token_used,
    mark_token_used,
)
from app.tasks.email import (
    send_password_reset_email_task,
    send_verification_email_task,
)

router = APIRouter(
    prefix="/auth",
    tags=["Authentication"],
)


@router.post(
    "/register",
    response_model=RegistrationResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(RateLimiter(times=5, seconds=60, scope="register"))],
)
def register_user(
    user_data: UserCreate,
    db: Session = Depends(get_db),
) -> RegistrationResponse:
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

    default_role = db.scalar(
        select(Role).where(Role.name == DEFAULT_USER_ROLE_NAME)
    )
    if default_role is not None:
        user.roles.append(default_role)

    db.add(user)
    db.commit()
    db.refresh(user)

    verification_token = create_email_verification_token(
        subject=str(user.id)
    )

    send_verification_email_task.delay(user.email, verification_token)

    return RegistrationResponse(
        id=user.id,
        email=user.email,
        is_active=user.is_active,
        is_verified=user.is_verified,
        message="Registration successful. Check your email to verify your account.",
    )


@router.post(
    "/login",
    response_model=TokenResponse,
    dependencies=[Depends(RateLimiter(times=5, seconds=60, scope="login"))],
)
def login_user(
    login_data: LoginRequest,
    db: Session = Depends(get_db),
) -> TokenResponse:
    email = str(login_data.email).lower()
    user = db.scalar(
        select(User).where(User.email == email)
    )

    if (
        user is None
        or user.hashed_password is None
        or not verify_password(login_data.password, user.hashed_password)
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    if not user.is_verified:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Email address is not verified",
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
    redis_client: Redis = Depends(get_redis),
) -> AccessTokenResponse:
    claims = decode_refresh_token(token_data.refresh_token)

    if claims is None or is_token_blacklisted(redis_client, claims.jti):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired refresh token",
        )

    user = db.scalar(
        select(User).where(User.email == claims.subject)
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


@router.post(
    "/logout",
    status_code=status.HTTP_204_NO_CONTENT,
)
def logout(
    body: LogoutRequest,
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
    redis_client: Redis = Depends(get_redis),
) -> Response:
    access_claims = decode_access_token(credentials.credentials)

    if access_claims is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired access token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    blacklist_token(
        redis_client,
        access_claims.jti,
        ttl_seconds=remaining_ttl_seconds(access_claims.expires_at),
    )

    if body.refresh_token is not None:
        refresh_claims = decode_refresh_token(body.refresh_token)

        if refresh_claims is not None:
            blacklist_token(
                redis_client,
                refresh_claims.jti,
                ttl_seconds=remaining_ttl_seconds(refresh_claims.expires_at),
            )

    return Response(status_code=status.HTTP_204_NO_CONTENT)

@router.get(
    "/verify-email",
    response_model=MessageResponse,
)
def verify_email(
    token: str,
    db: Session = Depends(get_db),
    redis_client: Redis = Depends(get_redis),
) -> MessageResponse:
    claims = decode_email_verification_token(token)

    if claims is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired verification token",
        )

    try:
        user_id = int(claims.subject)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid verification token subject",
        )

    user = db.get(User, user_id)

    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )

    if user.is_verified:
        return MessageResponse(
            message="Email is already verified"
        )

    if is_token_used(redis_client, claims.jti):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired verification token",
        )

    user.is_verified = True

    db.add(user)
    db.commit()

    mark_token_used(
        redis_client,
        claims.jti,
        ttl_seconds=remaining_ttl_seconds(claims.expires_at),
    )

    return MessageResponse(
        message="Email verified successfully"
    )

@router.post(
    "/forgot-password",
    response_model=ForgotPasswordResponse,
    dependencies=[Depends(RateLimiter(times=5, seconds=60, scope="forgot-password"))],
)
def forgot_password(
    request_data: ForgotPasswordRequest,
    db: Session = Depends(get_db),
) -> ForgotPasswordResponse:
    email = str(request_data.email).lower()

    user = db.scalar(
        select(User).where(User.email == email)
    )

    generic_message = (
        "If an account exists for this email, "
        "password reset instructions have been sent"
    )

    if user is not None and user.is_active:
        reset_token = create_password_reset_token(
            subject=str(user.id)
        )

        send_password_reset_email_task.delay(user.email, reset_token)

    return ForgotPasswordResponse(
        message=generic_message,
    )


@router.post(
    "/reset-password",
    response_model=MessageResponse,
)
def reset_password(
    request_data: ResetPasswordRequest,
    db: Session = Depends(get_db),
    redis_client: Redis = Depends(get_redis),
) -> MessageResponse:
    claims = decode_password_reset_token(
        request_data.token
    )

    if claims is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired password reset token",
        )

    if is_token_used(redis_client, claims.jti):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired password reset token",
        )

    try:
        user_id = int(claims.subject)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid password reset token subject",
        )

    user = db.get(User, user_id)

    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User account is inactive",
        )

    if user.hashed_password is not None and verify_password(
        request_data.new_password,
        user.hashed_password,
    ):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="New password must be different",
        )

    user.hashed_password = hash_password(
        request_data.new_password
    )

    db.add(user)
    db.commit()

    mark_token_used(
        redis_client,
        claims.jti,
        ttl_seconds=remaining_ttl_seconds(claims.expires_at),
    )

    return MessageResponse(
        message="Password reset successfully"
    )