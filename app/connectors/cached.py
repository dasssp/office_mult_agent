from __future__ import annotations

import json
from typing import Any

from app.connectors.base import KnowledgeConnector
from app.schemas import RequestContext
from app.services.cache import JsonCache, scoped_cache_key


class CachedKnowledgeConnector:
    """为知识检索结果提供权限隔离的短时缓存。"""

    def __init__(
        self,
        connector: KnowledgeConnector,
        cache: JsonCache,
        *,
        key_prefix: str,
        ttl_seconds: int,
    ) -> None:
        self._connector = connector
        self._cache = cache
        self._key_prefix = key_prefix
        self._ttl_seconds = ttl_seconds

    async def answer(
        self, *, query: str, context: RequestContext
    ) -> dict[str, Any]:
        permission_fingerprint = json.dumps(
            {
                "roles": sorted(context.role_ids),
                "scopes": sorted(context.permission_scopes),
            },
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        key = scoped_cache_key(
            prefix=self._key_prefix,
            namespace="knowledge-answer",
            tenant_id=context.tenant_id,
            parts=(
                context.operator_id,
                context.employee_id or "",
                permission_fingerprint,
                query.strip(),
            ),
        )
        cached = await self._cache.get(key)
        if isinstance(cached, dict):
            return cached

        result = await self._connector.answer(query=query, context=context)
        citations = result.get("citations")
        if isinstance(citations, list) and citations:
            await self._cache.set(key, result, ttl_seconds=self._ttl_seconds)
        return result

    async def aclose(self) -> None:
        close = getattr(self._connector, "aclose", None)
        if close is not None:
            await close()
