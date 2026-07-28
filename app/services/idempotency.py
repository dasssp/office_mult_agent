from typing import Protocol

from app.schemas import RequestContext


class IdempotencyRepository(Protocol):
    async def get(
        self, *, operation: str, key: str, context: RequestContext
    ) -> dict[str, object] | None: ...

    async def save(
        self,
        *,
        operation: str,
        key: str,
        result: dict[str, object],
        context: RequestContext,
    ) -> dict[str, object]: ...


class InMemoryIdempotencyRepository:
    def __init__(self) -> None:
        self._results: dict[tuple[str, str, str], dict[str, object]] = {}

    async def get(
        self, *, operation: str, key: str, context: RequestContext
    ) -> dict[str, object] | None:
        return self._results.get((context.tenant_id, operation, key))

    async def save(
        self,
        *,
        operation: str,
        key: str,
        result: dict[str, object],
        context: RequestContext,
    ) -> dict[str, object]:
        scope = (context.tenant_id, operation, key)
        existing = self._results.get(scope)
        if existing is not None:
            return existing
        self._results[scope] = result
        return result


class IdempotencyService:
    def __init__(self, repository: IdempotencyRepository | None = None) -> None:
        self._repository = repository or InMemoryIdempotencyRepository()

    async def get(
        self, *, operation: str, key: str, context: RequestContext
    ) -> dict[str, object] | None:
        return await self._repository.get(operation=operation, key=key, context=context)

    async def remember(
        self,
        *,
        operation: str,
        key: str,
        result: dict[str, object],
        context: RequestContext,
    ) -> dict[str, object]:
        return await self._repository.save(
            operation=operation,
            key=key,
            result=result,
            context=context,
        )
