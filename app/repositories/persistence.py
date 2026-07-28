from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.models import ApprovalTask, AuditLog, Report
from app.schemas import RequestContext
from app.schemas.workflows import ReportDraft
from app.services.approvals import ApprovalRecord


class SqlAlchemyReportRepository:
    def __init__(self, session_factory: async_sessionmaker) -> None:
        self._session_factory = session_factory

    async def save(self, draft: ReportDraft, context: RequestContext | None = None) -> ReportDraft:
        if context is None:
            raise ValueError("trusted request context is required for persistent reports")
        async with self._session_factory() as session:
            record = await session.get(Report, draft.report_id)
            if record is None:
                record = Report(
                    id=draft.report_id,
                    tenant_id=context.tenant_id,
                    created_by=context.operator_id,
                    report_date=draft.report_date,
                    status=draft.status,
                    payload=draft.model_dump(mode="json"),
                )
                session.add(record)
            else:
                if record.tenant_id != context.tenant_id:
                    raise KeyError(draft.report_id)
                record.status = draft.status
                record.payload = draft.model_dump(mode="json")
                record.version += 1
            await session.commit()
        return draft

    async def get(
        self, report_id: str, context: RequestContext | None = None
    ) -> ReportDraft | None:
        if context is None:
            raise ValueError("trusted request context is required for persistent reports")
        async with self._session_factory() as session:
            result = await session.execute(
                select(Report).where(Report.id == report_id, Report.tenant_id == context.tenant_id)
            )
            record = result.scalar_one_or_none()
            return ReportDraft.model_validate(record.payload) if record is not None else None


class SqlAlchemyAuditRepository:
    def __init__(self, session_factory: async_sessionmaker) -> None:
        self._session_factory = session_factory

    async def record(self, *, action: str, context: RequestContext, target_id: str) -> None:
        async with self._session_factory() as session:
            session.add(
                AuditLog(
                    action=action,
                    tenant_id=context.tenant_id,
                    created_by=context.operator_id,
                    target_id=target_id,
                    trace_id=context.trace_id,
                )
            )
            await session.commit()


class SqlAlchemyApprovalRepository:
    def __init__(self, session_factory: async_sessionmaker) -> None:
        self._session_factory = session_factory

    async def create_pending(
        self, *, target_type: str, target_id: str, context: RequestContext
    ) -> ApprovalRecord:
        async with self._session_factory() as session:
            result = await session.execute(
                select(ApprovalTask).where(
                    ApprovalTask.tenant_id == context.tenant_id,
                    ApprovalTask.target_type == target_type,
                    ApprovalTask.target_id == target_id,
                    ApprovalTask.status == "pending",
                )
            )
            record = result.scalar_one_or_none()
            if record is None:
                record = ApprovalTask(
                    tenant_id=context.tenant_id,
                    created_by=context.operator_id,
                    target_type=target_type,
                    target_id=target_id,
                    status="pending",
                )
                session.add(record)
                await session.commit()
            return self._to_record(record)

    async def get_pending(
        self, *, target_type: str, target_id: str, context: RequestContext
    ) -> ApprovalRecord | None:
        async with self._session_factory() as session:
            result = await session.execute(
                select(ApprovalTask).where(
                    ApprovalTask.tenant_id == context.tenant_id,
                    ApprovalTask.target_type == target_type,
                    ApprovalTask.target_id == target_id,
                    ApprovalTask.status == "pending",
                )
            )
            record = result.scalar_one_or_none()
            return self._to_record(record) if record is not None else None

    async def decide(
        self,
        *,
        target_type: str,
        target_id: str,
        approved: bool,
        comment: str | None,
        context: RequestContext,
    ) -> ApprovalRecord:
        async with self._session_factory() as session:
            result = await session.execute(
                select(ApprovalTask).where(
                    ApprovalTask.tenant_id == context.tenant_id,
                    ApprovalTask.target_type == target_type,
                    ApprovalTask.target_id == target_id,
                    ApprovalTask.status == "pending",
                )
            )
            record = result.scalar_one_or_none()
            if record is None:
                raise KeyError(target_id)
            record.status = "approved" if approved else "rejected"
            record.comment = comment
            record.version += 1
            await session.commit()
            return self._to_record(record)

    @staticmethod
    def _to_record(record: ApprovalTask) -> ApprovalRecord:
        return ApprovalRecord(
            target_type=record.target_type,
            target_id=record.target_id,
            tenant_id=record.tenant_id,
            status=record.status,
            comment=record.comment,
        )
