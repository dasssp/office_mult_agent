from uuid import uuid4

from app.schemas import RequestContext


class MockReportSystemConnector:
    def __init__(self) -> None:
        self._records: dict[str, dict] = {}

    async def get_projects(self, *, context: RequestContext) -> list[dict]:
        return [{"project_id": "project-demo", "name": "演示项目"}]

    async def get_work_types(self, *, context: RequestContext) -> list[dict]:
        return [{"work_type_id": "development", "name": "研发"}]

    async def get_report(
        self, *, report_id: str, context: RequestContext
    ) -> dict | None:
        return next(
            (
                record
                for record in self._records.values()
                if record["submission_id"] == report_id
                and record["tenant_id"] == context.tenant_id
            ),
            None,
        )

    async def submit_report(self, *, report: dict, idempotency_key: str, context: RequestContext) -> dict:
        existing = self._records.get(idempotency_key)
        if existing:
            return existing
        record = {"submission_id": str(uuid4()), "status": "submitted", "tenant_id": context.tenant_id, "report": report}
        self._records[idempotency_key] = record
        return record

    async def get_report_status(self, *, submission_id: str, context: RequestContext) -> dict:
        for record in self._records.values():
            if record["submission_id"] == submission_id and record["tenant_id"] == context.tenant_id:
                return {"submission_id": submission_id, "status": record["status"]}
        return {"submission_id": submission_id, "status": "not_found"}

    async def update_report(
        self,
        *,
        report_id: str,
        report: dict,
        idempotency_key: str,
        context: RequestContext,
    ) -> dict:
        current = await self.get_report(report_id=report_id, context=context)
        if current is None:
            raise KeyError(report_id)
        current["report"] = report
        return current
