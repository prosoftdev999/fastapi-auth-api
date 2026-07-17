from redis import Redis

_BLACKLIST_KEY_PREFIX = "blacklist:token:"
_USED_KEY_PREFIX = "used:token:"


def blacklist_token(redis_client: Redis, jti: str, ttl_seconds: int) -> None:
    """Revoke a token (e.g. on logout) until its natural expiry."""
    if ttl_seconds <= 0:
        return
    redis_client.set(f"{_BLACKLIST_KEY_PREFIX}{jti}", "1", ex=ttl_seconds)


def is_token_blacklisted(redis_client: Redis, jti: str) -> bool:
    return bool(redis_client.exists(f"{_BLACKLIST_KEY_PREFIX}{jti}"))


def mark_token_used(redis_client: Redis, jti: str, ttl_seconds: int) -> None:
    """Mark a single-use token (email verification / password reset) as spent."""
    if ttl_seconds <= 0:
        return
    redis_client.set(f"{_USED_KEY_PREFIX}{jti}", "1", ex=ttl_seconds)


def is_token_used(redis_client: Redis, jti: str) -> bool:
    return bool(redis_client.exists(f"{_USED_KEY_PREFIX}{jti}"))
