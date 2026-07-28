import os
from uuid import uuid4

import pytest

from app.services.cache import RedisJsonCache

pytestmark = pytest.mark.skipif(
    not os.getenv("TEST_REDIS_URL"),
    reason="TEST_REDIS_URL is required for Redis integration tests",
)


@pytest.mark.asyncio
async def test_redis_json_cache_round_trip_and_delete() -> None:
    cache = RedisJsonCache(os.environ["TEST_REDIS_URL"])
    key = f"office-multi-agent:test:{uuid4()}"
    value = {"status": "ok", "items": [1, 2, 3]}
    try:
        await cache.set(key, value, ttl_seconds=30)
        assert await cache.get(key) == value
        await cache.delete(key)
        assert await cache.get(key) is None
    finally:
        await cache.aclose()
