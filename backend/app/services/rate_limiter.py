"""Rate limiting service using Redis."""

import time
from typing import Tuple
import redis.asyncio as redis

from ..config import get_settings

settings = get_settings()

# Redis connection pool
redis_pool = None


async def get_redis() -> redis.Redis:
    """Get Redis connection."""
    global redis_pool
    if redis_pool is None:
        redis_pool = redis.from_url(
            settings.redis_url,
            encoding="utf-8",
            decode_responses=True
        )
    return redis_pool


async def check_rate_limit(
    connector_id: str,
    limit_per_minute: int,
    limit_per_hour: int
) -> Tuple[bool, dict]:
    """
    Check if a request is within rate limits using sliding window.
    
    Returns:
        (is_allowed, info_dict)
        is_allowed: True if request is allowed
        info_dict: Contains remaining limits and reset times
    """
    r = await get_redis()
    now = time.time()
    
    # Keys for minute and hour windows
    minute_key = f"rate:{connector_id}:minute"
    hour_key = f"rate:{connector_id}:hour"
    
    # Clean old entries and count current
    minute_start = now - 60
    hour_start = now - 3600
    
    pipe = r.pipeline()
    
    # Remove old entries
    pipe.zremrangebyscore(minute_key, 0, minute_start)
    pipe.zremrangebyscore(hour_key, 0, hour_start)
    
    # Count current entries
    pipe.zcard(minute_key)
    pipe.zcard(hour_key)
    
    results = await pipe.execute()
    minute_count = results[2]
    hour_count = results[3]
    
    # Check limits
    is_allowed = minute_count < limit_per_minute and hour_count < limit_per_hour
    
    info = {
        "minute_remaining": max(0, limit_per_minute - minute_count - 1),
        "hour_remaining": max(0, limit_per_hour - hour_count - 1),
        "minute_reset": int(now + 60),
        "hour_reset": int(now + 3600),
    }
    
    if is_allowed:
        # Add this request
        pipe = r.pipeline()
        pipe.zadd(minute_key, {str(now): now})
        pipe.zadd(hour_key, {str(now): now})
        pipe.expire(minute_key, 120)  # Keep for 2 minutes
        pipe.expire(hour_key, 7200)   # Keep for 2 hours
        await pipe.execute()
    
    return is_allowed, info


async def get_rate_limit_info(connector_id: str, limit_per_minute: int, limit_per_hour: int) -> dict:
    """Get current rate limit status without counting a request."""
    r = await get_redis()
    now = time.time()
    
    minute_key = f"rate:{connector_id}:minute"
    hour_key = f"rate:{connector_id}:hour"
    
    minute_start = now - 60
    hour_start = now - 3600
    
    pipe = r.pipeline()
    pipe.zcount(minute_key, minute_start, now)
    pipe.zcount(hour_key, hour_start, now)
    results = await pipe.execute()
    
    return {
        "minute_used": results[0],
        "minute_limit": limit_per_minute,
        "minute_remaining": max(0, limit_per_minute - results[0]),
        "hour_used": results[1],
        "hour_limit": limit_per_hour,
        "hour_remaining": max(0, limit_per_hour - results[1]),
    }
