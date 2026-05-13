"""Redis connection singleton."""

from functools import lru_cache

import redis

from queries.config import REDIS_URL


@lru_cache(maxsize=1)
def get_redis() -> redis.Redis:
    return redis.Redis.from_url(REDIS_URL, decode_responses=False)
