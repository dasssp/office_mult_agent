from dataclasses import dataclass
from typing import Protocol

from app.schemas import RequestContext


@dataclass(frozen=True)
class ApprovalRecord:
    target_type: str
    target_id: str
    tenant_id: str
    status: str = "pending"
    comment: str | None = None


class ApprovalRepository(Protocol):
    async def create_pending(
        self, *, target_type: str, target_id: str, context: RequestContext
    ) -> ApprovalRecord: ...

    async def get_pending(
        self, *, target_type: str, target_id: str, context: RequestContext
    ) -> ApprovalRecord | None: ...

    async def decide(
        self,
        *,
        target_type: str,
        target_id: str,
        approved: bool,
        comment: str | None,
        context: RequestContext,
    ) -> ApprovalRecord: ...


class InMemoryApprovalRepository:
    def __init__(self) -> None:
        self._records: dict[tuple[str, str, str], ApprovalRecord] = {}

    async def create_pending(
        self, *, target_type: str, target_id: str, context: RequestContext
    ) -> ApprovalRecord:
        record = ApprovalRecord(
            target_type=target_type,
            target_id=target_id,
            tenant_id=context.tenant_id,
        )
        self._records[(context.tenant_id, target_type, target_id)] = record
        return record

    async def get_pending(
        self, *, target_type: str, target_id: str, context: RequestContext
    ) -> ApprovalRecord | None:
        record = self._records.get((context.tenant_id, target_type, target_id))
        return record if record is not None and record.status == "pending" else None

    async def decide(
        self,
        *,
        target_type: str,
        target_id: str,
        approved: bool,
        comment: str | None,
        context: RequestContext,
    ) -> ApprovalRecord:
        current = await self.get_pending(
            target_type=target_type, target_id=target_id, context=context
        )
        if current is None:
            raise KeyError(target_id)
        record = ApprovalRecord(
            target_type=target_type,
            target_id=target_id,
            tenant_id=context.tenant_id,
            status="approved" if approved else "rejected",
            comment=comment,
        )
        self._records[(context.tenant_id, target_type, target_id)] = record
        return record


class ApprovalService:
    def __init__(self, repository: ApprovalRepository | None = None) -> None:
        self._repository = repository or InMemoryApprovalRepository()

    async def request(
        self, *, target_type: str, target_id: str, context: RequestContext
    ) -> ApprovalRecord:
        return await self._repository.create_pending(
            target_type=target_type, target_id=target_id, context=context
        )

    async def require_pending(
        self, *, target_type: str, target_id: str, context: RequestContext
    ) -> ApprovalRecord:
        record = await self._repository.get_pending(
            target_type=target_type, target_id=target_id, context=context
        )
        if record is None:
            raise KeyError(target_id)
        return record

    async def decide(
        self,
        *,
        target_type: str,
        target_id: str,
        approved: bool,
        comment: str | None,
        context: RequestContext,
    ) -> ApprovalRecord:
        return await self._repository.decide(
            target_type=target_type,
            target_id=target_id,
            approved=approved,
            comment=comment,
            context=context,
        )
