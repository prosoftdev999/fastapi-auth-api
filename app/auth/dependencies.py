from fastapi import Depends, HTTPException, Query, WebSocket, WebSocketException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from redis import Redis
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.jwt import decode_access_token
from app.core.redis_client import get_redis
from app.db.session import get_db
from app.models.user import User
from app.services.token_blacklist import is_token_blacklisted

bearer_scheme = HTTPBearer()


def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
    db: Session = Depends(get_db),
    redis_client: Redis = Depends(get_redis),
) -> User:
    claims = decode_access_token(credentials.credentials)

    if claims is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired access token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if is_token_blacklisted(redis_client, claims.jti):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has been revoked",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user = db.scalar(
        select(User).where(User.email == claims.subject)
    )

    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User account is inactive",
        )

    return user


def get_current_user_ws(
    websocket: WebSocket,
    token: str = Query(...),
    db: Session = Depends(get_db),
    redis_client: Redis = Depends(get_redis),
) -> User:
    """WebSocket equivalent of get_current_user.

    Browsers can't set an Authorization header on a WebSocket handshake, so
    the access token travels as a query param instead. Failures raise
    WebSocketException (closes the socket with a policy-violation code)
    rather than HTTPException, which has no meaning once the connection has
    upgraded.
    """
    claims = decode_access_token(token)

    if claims is None or is_token_blacklisted(redis_client, claims.jti):
        raise WebSocketException(code=status.WS_1008_POLICY_VIOLATION)

    user = db.scalar(select(User).where(User.email == claims.subject))

    if user is None or not user.is_active:
        raise WebSocketException(code=status.WS_1008_POLICY_VIOLATION)

    return user
