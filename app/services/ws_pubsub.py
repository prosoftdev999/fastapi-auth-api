import asyncio
import json
import logging

import redis.asyncio as aioredis

from app.core.config import settings
from app.services.connection_manager import USER_CHANNEL_PREFIX, manager

logger = logging.getLogger("app.websocket")


def get_async_redis() -> aioredis.Redis:
    return aioredis.from_url(settings.redis_url, decode_responses=True)


async def publish_to_user(user_id: int, message: dict) -> None:
    """Deliver `message` to user_id's connection(s), best-effort.

    Tries local delivery first (the common case, and the only thing that
    works without a real Redis server — this is what the test suite
    exercises). Falls back to a Redis pub/sub publish so a *different*
    worker process holding that user's actual connection can pick it up.

    Never raises: this is a side channel off the back of real operations
    (e.g. an admin granting a role) — failing to push a live notification
    must never fail the operation that triggered it.
    """
    delivered_locally = await manager.send_local(user_id, message)
    if delivered_locally:
        return

    try:
        client = get_async_redis()
        try:
            await client.publish(
                f"{USER_CHANNEL_PREFIX}{user_id}", json.dumps(message)
            )
        finally:
            await client.aclose()
    except Exception:
        logger.warning(
            "failed to publish ws notification, dropping",
            extra={"user_id": user_id},
            exc_info=True,
        )


async def run_pubsub_listener() -> None:
    """Background task, started at app startup: fans Redis pub/sub messages
    out to this worker's local WebSocket connections. Only matters when
    running with more than one worker process (see docker-compose.prod.yml's
    Gunicorn WEB_CONCURRENCY). Retries indefinitely if Redis is briefly
    unreachable rather than dying on the first connection error.
    """
    while True:
        try:
            client = get_async_redis()
            pubsub = client.pubsub()
            await pubsub.psubscribe(f"{USER_CHANNEL_PREFIX}*")

            try:
                async for item in pubsub.listen():
                    if item["type"] != "pmessage":
                        continue

                    channel = item["channel"]
                    try:
                        user_id = int(channel.removeprefix(USER_CHANNEL_PREFIX))
                        message = json.loads(item["data"])
                    except (ValueError, json.JSONDecodeError):
                        logger.warning(
                            "dropped malformed ws pubsub message",
                            extra={"channel": channel},
                        )
                        continue

                    await manager.send_local(user_id, message)
            finally:
                await pubsub.aclose()
                await client.aclose()
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("ws pubsub listener crashed, retrying in 5s")
            await asyncio.sleep(5)
