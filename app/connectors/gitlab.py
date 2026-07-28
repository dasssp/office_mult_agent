import json
from datetime import date, timedelta
from typing import Any
from urllib.parse import quote

import httpx

from app.connectors.base import GitLabConnector
from app.schemas import RequestContext
from app.services.cache import JsonCache, scoped_cache_key


class GitLabConnectorError(RuntimeError):
    pass


class GitLabHttpConnector:
    """Read-only GitLab Events API connector."""

    def __init__(
        self,
        *,
        base_url: str,
        access_token: str,
        timeout_seconds: float = 10,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._owns_client = client is None
        self._access_token = access_token
        self._client = client or httpx.AsyncClient(
            base_url=f"{base_url.rstrip('/')}/api/v4",
            timeout=timeout_seconds,
        )

    async def list_activity(
        self,
        *,
        employee_id: str,
        date_from: str,
        date_to: str,
        context: RequestContext,
    ) -> list[dict]:
        del context
        try:
            before = (date.fromisoformat(date_to) + timedelta(days=1)).isoformat()
            response = await self._client.get(
                f"/users/{quote(employee_id, safe='')}/events",
                headers={"PRIVATE-TOKEN": self._access_token},
                params={
                    "after": date_from,
                    "before": before,
                    "sort": "asc",
                    "per_page": 100,
                },
            )
            response.raise_for_status()
            events = response.json()
        except (httpx.HTTPError, ValueError) as error:
            raise GitLabConnectorError("GitLab 活动查询失败") from error
        if not isinstance(events, list):
            raise GitLabConnectorError("GitLab 活动响应格式无效")
        return [self._normalize_event(item) for item in events if isinstance(item, dict)]

    @staticmethod
    def _normalize_event(event: dict[str, Any]) -> dict[str, object]:
        push_data = event.get("push_data")
        commit_title = (
            str(push_data.get("commit_title", ""))
            if isinstance(push_data, dict)
            else ""
        )
        target_title = str(event.get("target_title", ""))
        action_name = str(event.get("action_name", "GitLab 活动"))
        title = commit_title or target_title or action_name
        return {
            "id": str(event.get("id", "")),
            "type": str(event.get("target_type") or event.get("action_name") or "event"),
            "title": title,
            "project_id": event.get("project_id"),
            "created_at": event.get("created_at"),
        }

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()


class CachedGitLabConnector:
    def __init__(
        self,
        connector: GitLabConnector,
        cache: JsonCache,
        *,
        key_prefix: str,
        ttl_seconds: int,
    ) -> None:
        self._connector = connector
        self._cache = cache
        self._key_prefix = key_prefix
        self._ttl_seconds = ttl_seconds

    async def list_activity(
        self,
        *,
        employee_id: str,
        date_from: str,
        date_to: str,
        context: RequestContext,
    ) -> list[dict]:
        key = scoped_cache_key(
            prefix=self._key_prefix,
            namespace="gitlab-activity",
            tenant_id=context.tenant_id,
            parts=(
                context.operator_id,
                employee_id,
                date_from,
                date_to,
                json.dumps(
                    {
                        "roles": sorted(context.role_ids),
                        "scopes": sorted(context.permission_scopes),
                    },
                    sort_keys=True,
                    separators=(",", ":"),
                ),
            ),
        )
        cached = await self._cache.get(key)
        if isinstance(cached, list) and all(isinstance(item, dict) for item in cached):
            return cached
        result = await self._connector.list_activity(
            employee_id=employee_id,
            date_from=date_from,
            date_to=date_to,
            context=context,
        )
        await self._cache.set(key, result, ttl_seconds=self._ttl_seconds)
        return result

    async def aclose(self) -> None:
        close = getattr(self._connector, "aclose", None)
        if close is not None:
            await close()
