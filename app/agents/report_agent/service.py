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
        self,
        *,
        report_date: str,
        events: list[WorkEvent],
        context: RequestContext | None = None,
        source_warnings: list[str] | None = None,
    ) -> ReportDraft:
        events = self._deduplicate(events)
        completed = [event for event in events if event.status == "completed"]
        in_progress = [event for event in events if event.status == "in_progress"]
        blocked = [event for event in events if event.status == "blocked"]
        draft = ReportDraft(
            report_date=report_date,
            completed=[self._report_line(event) for event in completed],
            in_progress=[self._report_line(event) for event in in_progress],
            risks=[self._report_line(event) for event in blocked],
            plans=[
                self._report_line(event)
                for event in events
                if event.status == "planned"
            ],
            evidence_event_ids=[event.event_id for event in events],
            overview=f"共汇总 {len(events)} 项有证据的工作事件。",
            source_warnings=[
                *(source_warnings or []),
                *[
                    f"事件 {event.event_id} 状态或证据可信度需要确认"
                    for event in events
                    if event.status == "unknown" or event.confidence < 0.6
                ],
            ],
            status="draft",
        )
        return await self.repository.save(draft, context)

    async def generate_weekly(
        self,
        *,
        week_start: str,
        events: list[WorkEvent],
        context: RequestContext | None = None,
        source_warnings: list[str] | None = None,
    ) -> ReportDraft:
        draft = await self.generate_daily(
            report_date=week_start,
            events=events,
            context=context,
            source_warnings=source_warnings,
        )
        draft.report_type = "weekly"
        draft.overview = f"本周共汇总 {len(draft.evidence_event_ids)} 项去重后的工作事件。"
        return await self.repository.save(draft, context)

    @staticmethod
    def _deduplicate(events: list[WorkEvent]) -> list[WorkEvent]:
        selected: dict[tuple[str | None, str], WorkEvent] = {}
        for event in events:
            key = (event.project_id, " ".join(event.title.lower().split()))
            current = selected.get(key)
            if current is None or event.confidence > current.confidence:
                selected[key] = event
        return list(selected.values())

    @staticmethod
    def _report_line(event: WorkEvent) -> str:
        detail = (event.result or event.description or "").strip()
        if not detail or detail in event.title:
            return event.title
        return f"{event.title}：{detail[:200]}"

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
