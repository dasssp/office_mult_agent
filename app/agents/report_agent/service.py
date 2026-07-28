from app.connectors.base import ReportSystemConnector
from app.connectors.mocks.work_sources import MockWorkSources
from app.repositories.persistence import SqlAlchemyReportRepository
from app.repositories.reports import InMemoryReportRepository
from app.schemas import RequestContext
from app.schemas.workflows import ReportDraft, ReportSubmission, WorkEvent
from app.services.audit import AuditService
from app.services.idempotency import IdempotencyService
from app.services.permissions import PermissionService
from app.services.sensitive_data import SensitiveDataService


class ReportAgent:
    def __init__(
        self,
        repository: InMemoryReportRepository | SqlAlchemyReportRepository | None = None,
        idempotency: IdempotencyService | None = None,
    ) -> None:
        self.repository = repository or InMemoryReportRepository()
        self._idempotency = idempotency or IdempotencyService()
        self._sensitive_data = SensitiveDataService()

    async def collect_mock_events(self) -> list[WorkEvent]:
        return await MockWorkSources().collect_events()

    async def generate_daily(
        self, *, report_date: str, events: list[WorkEvent], context: RequestContext | None = None
    ) -> ReportDraft:
        completed = [event for event in events if event.status == "completed"]
        in_progress = [event for event in events if event.status == "in_progress"]
        blocked = [event for event in events if event.status == "blocked"]
        draft = ReportDraft(
            report_date=report_date,
            completed=[event.title for event in completed],
            in_progress=[event.title for event in in_progress],
            risks=[event.title for event in blocked],
            evidence_event_ids=[event.event_id for event in events],
            status="draft",
        )
        return await self.repository.save(draft, context)

    async def review(self, *, report_id: str, approved: bool, comment: str | None, context: RequestContext, permissions: PermissionService, audit: AuditService) -> ReportDraft:
        permissions.require(context, "report:review")
        draft = await self.repository.get(report_id, context)
        if draft is None:
            raise KeyError(report_id)
        draft.status = "approved" if approved else "rejected"
        draft.review_comment = comment
        await audit.record(action="report.review", context=context, target_id=report_id)
        return await self.repository.save(draft, context)

    async def submit(
        self, *, report_id: str, context: RequestContext, connector: ReportSystemConnector,
        permissions: PermissionService, audit: AuditService,
    ) -> ReportSubmission:
        permissions.require(context, "report:submit")
        draft = await self.repository.get(report_id, context)
        if draft is None:
            raise KeyError(report_id)
        existing = await self._idempotency.get(
            operation="report.submit", key=report_id, context=context
        )
        if existing is not None:
            return ReportSubmission.model_validate(existing)
        if draft.status != "approved":
            raise ValueError("report must be approved before submission")
        self._sensitive_data.require_shareable(str(draft.model_dump(mode="json")))
        key = f"{context.tenant_id}:{context.employee_id}:{draft.report_date}:{report_id}"
        result = await connector.submit_report(report=draft.model_dump(), idempotency_key=key, context=context)
        draft.status = "submitted"
        await self.repository.save(draft, context)
        await audit.record(action="report.submit", context=context, target_id=report_id)
        submission = ReportSubmission(report_id=report_id, submission_id=result["submission_id"], status="submitted")
        stored = await self._idempotency.remember(
            operation="report.submit",
            key=report_id,
            result=submission.model_dump(mode="json"),
            context=context,
        )
        return ReportSubmission.model_validate(stored)
