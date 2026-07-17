from fastapi import Depends, HTTPException, Request, status
from redis import Redis

from app.core.redis_client import get_redis


class RateLimiter:
    """Fixed-window rate limiter keyed by client IP, backed by Redis INCR/EXPIRE.

    Usage: Depends(RateLimiter(times=5, seconds=60, scope="login"))
    """

    def __init__(self, times: int, seconds: int, scope: str) -> None:
        self.times = times
        self.seconds = seconds
        self.scope = scope

    def __call__(
        self,
        request: Request,
        redis_client: Redis = Depends(get_redis),
    ) -> None:
        client_host = request.client.host if request.client else "unknown"
        key = f"ratelimit:{self.scope}:{client_host}"

        current = redis_client.incr(key)

        if current == 1:
            redis_client.expire(key, self.seconds)

        if current > self.times:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Too many requests. Please try again later.",
            )
