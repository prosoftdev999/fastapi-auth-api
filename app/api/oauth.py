import secrets

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from redis import Redis
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from starlette.responses import RedirectResponse

from app.auth.dependencies import get_current_user
from app.auth.jwt import create_access_token, create_refresh_token
from app.core.oauth import SUPPORTED_PROVIDERS, OAuthProviderClient, get_oauth_client
from app.core.redis_client import get_redis
from app.db.session import get_db
from app.models.oauth_account import OAuthAccount
from app.models.user import User
from app.schemas.oauth import LinkedProviderResponse
from app.schemas.token import TokenResponse

router = APIRouter(prefix="/auth/oauth", tags=["OAuth"])

_STATE_TTL_SECONDS = 600
_STATE_KEY_PREFIX = "oauth:state:"


def _callback_url(request: Request, provider: str) -> str:
    return str(request.url_for("oauth_callback", provider=provider))


def _require_client(provider: str) -> OAuthProviderClient:
    if provider not in SUPPORTED_PROVIDERS:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Unknown OAuth provider",
        )

    client = get_oauth_client(provider)

    if client is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"OAuth provider '{provider}' is not configured",
        )

    return client


@router.get("/{provider}/login")
async def oauth_login(
    provider: str,
    request: Request,
    redis_client: Redis = Depends(get_redis),
) -> RedirectResponse:
    client = _require_client(provider)

    state = secrets.token_urlsafe(32)
    redis_client.set(f"{_STATE_KEY_PREFIX}{state}", "login", ex=_STATE_TTL_SECONDS)

    redirect_uri = _callback_url(request, provider)
    authorization_url = await client.create_authorization_url(redirect_uri, state)

    return RedirectResponse(authorization_url)


@router.get("/{provider}/link")
async def oauth_link(
    provider: str,
    request: Request,
    current_user: User = Depends(get_current_user),
    redis_client: Redis = Depends(get_redis),
) -> RedirectResponse:
    client = _require_client(provider)

    state = secrets.token_urlsafe(32)
    redis_client.set(
        f"{_STATE_KEY_PREFIX}{state}",
        f"link:{current_user.id}",
        ex=_STATE_TTL_SECONDS,
    )

    redirect_uri = _callback_url(request, provider)
    authorization_url = await client.create_authorization_url(redirect_uri, state)

    return RedirectResponse(authorization_url)


@router.get(
    "/{provider}/callback",
    name="oauth_callback",
    response_model=TokenResponse,
)
async def oauth_callback(
    provider: str,
    request: Request,
    code: str = Query(...),
    state: str = Query(...),
    db: Session = Depends(get_db),
    redis_client: Redis = Depends(get_redis),
) -> TokenResponse:
    client = _require_client(provider)

    state_key = f"{_STATE_KEY_PREFIX}{state}"
    state_value = redis_client.get(state_key)

    if state_value is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired OAuth state",
        )

    redis_client.delete(state_key)

    redirect_uri = _callback_url(request, provider)
    token = await client.fetch_access_token(redirect_uri, code)
    provider_user_id, email = await client.fetch_identity(token)

    linking_user_id: int | None = None
    if state_value.startswith("link:"):
        linking_user_id = int(state_value.split(":", 1)[1])

    existing_link = db.scalar(
        select(OAuthAccount).where(
            OAuthAccount.provider == provider,
            OAuthAccount.provider_user_id == provider_user_id,
        )
    )

    if linking_user_id is not None:
        if existing_link is not None and existing_link.user_id != linking_user_id:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="This provider account is already linked to another user",
            )

        user = db.get(User, linking_user_id)
        if user is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="User not found"
            )

        if existing_link is None:
            db.add(
                OAuthAccount(
                    user_id=user.id,
                    provider=provider,
                    provider_user_id=provider_user_id,
                    email=email,
                )
            )
            db.commit()
    else:
        if existing_link is not None:
            user = db.get(User, existing_link.user_id)
        else:
            if email is None:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"{provider} did not provide an email address",
                )

            user = db.scalar(select(User).where(User.email == email))

            if user is None:
                user = User(
                    email=email,
                    hashed_password=None,
                    is_active=True,
                    is_verified=True,
                )
                db.add(user)
                db.commit()
                db.refresh(user)

            db.add(
                OAuthAccount(
                    user_id=user.id,
                    provider=provider,
                    provider_user_id=provider_user_id,
                    email=email,
                )
            )
            db.commit()

        if user is None or not user.is_active:
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


@router.get("/accounts", response_model=list[LinkedProviderResponse])
def list_linked_accounts(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[OAuthAccount]:
    return list(
        db.scalars(
            select(OAuthAccount).where(OAuthAccount.user_id == current_user.id)
        )
    )


@router.delete("/{provider}", status_code=status.HTTP_204_NO_CONTENT)
def unlink_provider(
    provider: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Response:
    link = db.scalar(
        select(OAuthAccount).where(
            OAuthAccount.user_id == current_user.id,
            OAuthAccount.provider == provider,
        )
    )

    if link is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Provider is not linked",
        )

    remaining_links = db.scalar(
        select(func.count(OAuthAccount.id)).where(
            OAuthAccount.user_id == current_user.id
        )
    )

    if current_user.hashed_password is None and remaining_links <= 1:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "Cannot unlink the only sign-in method. "
                "Set a password first via the password reset flow."
            ),
        )

    db.delete(link)
    db.commit()

    return Response(status_code=status.HTTP_204_NO_CONTENT)
