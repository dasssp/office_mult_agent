from dataclasses import dataclass
from typing import Generic, TypeVar

from app.schemas import RequestContext

T = TypeVar("T")


@dataclass
class IdempotencyService(Generic[T]):
    """Tenant-scoped result cache used around externally visible write operations."""

    def __post_init__(self) -> None:
        self._results: dict[tuple[str, str], T] = {}

    def get(self, key: str, context: RequestContext) -> T | None:
        return self._results.get((context.tenant_id, key))

    def remember(self, key: str, result: T, context: RequestContext) -> T:
        self._results[(context.tenant_id, key)] = result
        return result
