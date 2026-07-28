from app.connectors.base import ReportSystemConnector
from app.connectors.mocks.work_sources import MockWorkSources
from app.repositories.reports import InMemoryReportRepository
from app.schemas import RequestContext
from app.schemas.workflows import ReportDraft, ReportSubmission, WorkEvent
from app.services.audit import AuditService
from app.services.permissions import PermissionService


class ReportAgent:
    def __init__(self, repository: InMemoryReportRepository | None = None) -> None:
        self.repository = repository or InMemoryReportRepository()
        self._submissions: dict[str, ReportSubmission] = {}

    async def collect_mock_events(self) -> list[WorkEvent]:
        return await MockWorkSources().collect_events()

    async def generate_daily(self, *, report_date: str, events: list[WorkEvent]) -> ReportDraft:
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
        return await self.repository.save(draft)

    async def review(self, *, report_id: str, approved: bool, comment: str | None) -> ReportDraft:
        draft = await self.repository.get(report_id)
        if draft is None:
            raise KeyError(report_id)
        draft.status = "approved" if approved else "rejected"
        draft.review_comment = comment
        return await self.repository.save(draft)

    async def submit(
        self, *, report_id: str, context: RequestContext, connector: ReportSystemConnector,
        permissions: PermissionService, audit: AuditService,
    ) -> ReportSubmission:
        permissions.require(context, "report:submit")
        draft = await self.repository.get(report_id)
        if draft is None:
            raise KeyError(report_id)
        existing = self._submissions.get(report_id)
        if existing is not None:
            return existing
        if draft.status != "approved":
            raise ValueError("report must be approved before submission")
        key = f"{context.tenant_id}:{context.employee_id}:{draft.report_date}:{report_id}"
        result = await connector.submit_report(report=draft.model_dump(), idempotency_key=key, context=context)
        draft.status = "submitted"
        await self.repository.save(draft)
        audit.record(action="report.submit", context=context, target_id=report_id)
        submission = ReportSubmission(report_id=report_id, submission_id=result["submission_id"], status="submitted")
        self._submissions[report_id] = submission
        return submission
