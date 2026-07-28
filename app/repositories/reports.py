from app.schemas.workflows import ReportDraft


class InMemoryReportRepository:
    def __init__(self) -> None:
        self._reports: dict[str, ReportDraft] = {}

    async def save(self, draft: ReportDraft) -> ReportDraft:
        self._reports[draft.report_id] = draft
        return draft

    async def get(self, report_id: str) -> ReportDraft | None:
        return self._reports.get(report_id)
