from datetime import UTC, datetime

import pytest

from app.connectors.cached import CachedKnowledgeConnector
from app.connectors.gitlab import CachedGitLabConnector
from app.schemas import RequestContext
from app.services.cache import InMemoryJsonCache, scoped_cache_key
from app.services.runtime_state import (
    ConfirmedMemory,
    InMemoryRuntimeStateRepository,
    MemoryService,
)


def _context(tenant_id: str = "tenant-a") -> RequestContext:
    return RequestContext(
        thread_id="thread-1",
        tenant_id=tenant_id,
        operator_id="operator-a",
        employee_id="gitlab-user",
    )


class _CountingGitLabConnector:
    def __init__(self) -> None:
        self.calls = 0

    async def list_activity(
        self,
        *,
        employee_id: str,
        date_from: str,
        date_to: str,
        context: RequestContext,
    ) -> list[dict]:
        self.calls += 1
        return [
            {
                "id": f"{context.tenant_id}:{employee_id}",
                "title": "GitLab 合并请求",
                "type": "merge_request",
            }
        ]


@pytest.mark.asyncio
async def test_gitlab_cache_is_tenant_scoped() -> None:
    source = _CountingGitLabConnector()
    connector = CachedGitLabConnector(
        source,
        InMemoryJsonCache(),
        key_prefix="test",
        ttl_seconds=60,
    )
    arguments = {
        "employee_id": "gitlab-user",
        "date_from": "2026-07-28",
        "date_to": "2026-07-28",
    }
    first = await connector.list_activity(**arguments, context=_context())
    second = await connector.list_activity(**arguments, context=_context())
    other_tenant = await connector.list_activity(
        **arguments,
        context=_context("tenant-b"),
    )

    assert first == second
    assert first != other_tenant
    assert source.calls == 2


class _CountingKnowledgeConnector:
    def __init__(self, *, with_citations: bool = True) -> None:
        self.calls = 0
        self.with_citations = with_citations

    async def answer(
        self, *, query: str, context: RequestContext
    ) -> dict[str, object]:
        self.calls += 1
        return {
            "answer": f"{context.tenant_id}:{query}",
            "citations": [{"source": "handbook"}] if self.with_citations else [],
        }


@pytest.mark.asyncio
async def test_knowledge_cache_is_permission_scoped() -> None:
    source = _CountingKnowledgeConnector()
    connector = CachedKnowledgeConnector(
        source,
        InMemoryJsonCache(),
        key_prefix="test",
        ttl_seconds=60,
    )
    context = _context()
    context.role_ids = ["employee"]
    context.permission_scopes = {"knowledge:read"}

    first = await connector.answer(query="报销规则", context=context)
    second = await connector.answer(query="报销规则", context=context)
    privileged = context.model_copy(
        update={"role_ids": ["finance"], "permission_scopes": {"knowledge:read:all"}}
    )
    await connector.answer(query="报销规则", context=privileged)

    assert first == second
    assert source.calls == 2


@pytest.mark.asyncio
async def test_knowledge_result_without_citations_is_not_cached() -> None:
    source = _CountingKnowledgeConnector(with_citations=False)
    connector = CachedKnowledgeConnector(
        source,
        InMemoryJsonCache(),
        key_prefix="test",
        ttl_seconds=60,
    )

    await connector.answer(query="未知问题", context=_context())
    await connector.answer(query="未知问题", context=_context())

    assert source.calls == 2


class _CountingMemoryRepository(InMemoryRuntimeStateRepository):
    def __init__(self) -> None:
        super().__init__()
        self.list_calls = 0

    async def list_memories(
        self, context: RequestContext
    ) -> list[ConfirmedMemory]:
        self.list_calls += 1
        return await super().list_memories(context)


@pytest.mark.asyncio
async def test_confirmed_memory_cache_invalidates_after_write() -> None:
    repository = _CountingMemoryRepository()
    cache = InMemoryJsonCache()
    service = MemoryService(repository, cache=cache)
    context = _context()

    assert await service.list_for(context) == []
    assert await service.list_for(context) == []
    assert repository.list_calls == 1

    await service.remember(
        key="report_style",
        value="简洁",
        confirmed=True,
        context=context,
    )
    memories = await service.list_for(context)
    assert repository.list_calls == 2
    assert memories[0].value == "简洁"


def test_cache_key_hides_tenant_and_identity() -> None:
    key = scoped_cache_key(
        prefix="office",
        namespace="memory",
        tenant_id="sensitive-tenant",
        parts=("employee@example.com", datetime.now(UTC).isoformat()),
    )
    assert "sensitive-tenant" not in key
    assert "employee@example.com" not in key
