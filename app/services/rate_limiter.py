"""
Redis-based rate limiter for widget endpoints.

Uses sliding window counters per IP and per session.
"""
import logging

import redis.asyncio as redis

from app.config import settings

logger = logging.getLogger(__name__)

_redis_client: redis.Redis | None = None


async def get_redis() -> redis.Redis:
    """Get or create the Redis client singleton."""
    global _redis_client
    if _redis_client is None:
        _redis_client = redis.from_url(settings.REDIS_URL, decode_responses=True)
    return _redis_client


async def check_rate_limit(
    identifier: str,
    limit: int,
    window_seconds: int,
    prefix: str = "rl",
) -> bool:
    """
    Check if the identifier is within the rate limit.
    Returns True if the request is allowed, False if rate-limited.
    """
    try:
        r = await get_redis()
        key = f"{prefix}:{identifier}"
        current = await r.get(key)

        if current is not None and int(current) >= limit:
            return False

        pipe = r.pipeline()
        pipe.incr(key)
        pipe.expire(key, window_seconds)
        await pipe.execute()
        return True
    except Exception as e:
        logger.warning(f"[RateLimiter] Redis error (allowing request): {e}")
        # If Redis is down, allow the request (fail-open)
        return True


async def check_widget_rate_limit(client_ip: str, session_id: str | None = None) -> bool:
    """
    Check widget rate limits:
    - Per-IP: WIDGET_RATE_LIMIT_PER_MINUTE requests per minute
    - Per-session: WIDGET_RATE_LIMIT_PER_HOUR requests per hour (if session_id provided)

    Returns True if allowed, False if rate-limited.
    """
    # Check per-IP limit (per minute)
    ip_allowed = await check_rate_limit(
        identifier=client_ip,
        limit=settings.WIDGET_RATE_LIMIT_PER_MINUTE,
        window_seconds=60,
        prefix="rl:widget:ip",
    )
    if not ip_allowed:
        return False

    # Check per-session limit (per hour)
    if session_id:
        session_allowed = await check_rate_limit(
            identifier=session_id,
            limit=settings.WIDGET_RATE_LIMIT_PER_HOUR,
            window_seconds=3600,
            prefix="rl:widget:session",
        )
        if not session_allowed:
            return False

    return True
