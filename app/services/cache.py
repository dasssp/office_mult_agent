import asyncio
import hashlib
import json
from copy import deepcopy
from typing import Protocol

from redis.asyncio import Redis
from redis.exceptions import RedisError


class JsonCache(Protocol):
    async def get(self, key: str) -> object | None: ...

    async def set(self, key: str, value: object, *, ttl_seconds: int) -> None: ...

    async def delete(self, key: str) -> None: ...

    async def aclose(self) -> None: ...


def scoped_cache_key(
    *,
    prefix: str,
    namespace: str,
    tenant_id: str,
    parts: tuple[str, ...],
) -> str:
    """Build a tenant-scoped key without exposing identity or query text."""
    serialized = json.dumps(
        [tenant_id, *parts],
        ensure_ascii=False,
        separators=(",", ":"),
    )
    digest = hashlib.sha256(serialized.encode("utf-8")).hexdigest()
    return f"{prefix}:{namespace}:v1:{digest}"


class RedisJsonCache:
    """Fail-open Redis cache; PostgreSQL and connectors remain the source of truth."""

    def __init__(
        self,
        redis_url: str,
        *,
        socket_timeout_seconds: float = 0.5,
    ) -> None:
        self._client = Redis.from_url(
            redis_url,
            decode_responses=True,
            socket_connect_timeout=socket_timeout_seconds,
            socket_timeout=socket_timeout_seconds,
            health_check_interval=30,
        )

    async def get(self, key: str) -> object | None:
        try:
            value = await self._client.get(key)
        except RedisError:
            return None
        if value is None:
            return None
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            await self.delete(key)
            return None

    async def set(self, key: str, value: object, *, ttl_seconds: int) -> None:
        try:
            encoded = json.dumps(
                value,
                ensure_ascii=False,
                separators=(",", ":"),
            )
            await self._client.set(key, encoded, ex=max(1, ttl_seconds))
        except (RedisError, TypeError, ValueError):
            return

    async def delete(self, key: str) -> None:
        try:
            await self._client.delete(key)
        except RedisError:
            return

    async def aclose(self) -> None:
        await self._client.aclose()


class InMemoryJsonCache:
    """Deterministic cache double used by unit tests and local no-Redis flows."""

    def __init__(self) -> None:
        self._values: dict[str, object] = {}
        self._lock = asyncio.Lock()

    async def get(self, key: str) -> object | None:
        async with self._lock:
            value = self._values.get(key)
            return deepcopy(value)

    async def set(self, key: str, value: object, *, ttl_seconds: int) -> None:
        if ttl_seconds < 1:
            return
        async with self._lock:
            self._values[key] = deepcopy(value)

    async def delete(self, key: str) -> None:
        async with self._lock:
            self._values.pop(key, None)

    async def aclose(self) -> None:
        return
