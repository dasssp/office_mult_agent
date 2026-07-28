from dataclasses import dataclass, field

from app.repositories.persistence import SqlAlchemyAuditRepository
from app.schemas import RequestContext


@dataclass(frozen=True)
class AuditRecord:
    action: str
    tenant_id: str
    operator_id: str
    target_id: str


@dataclass
class AuditService:
    records: list[AuditRecord] = field(default_factory=list)
    repository: SqlAlchemyAuditRepository | None = None

    async def record(self, *, action: str, context: RequestContext, target_id: str) -> None:
        self.records.append(AuditRecord(action, context.tenant_id, context.operator_id, target_id))
        if self.repository is not None:
            await self.repository.record(action=action, context=context, target_id=target_id)
