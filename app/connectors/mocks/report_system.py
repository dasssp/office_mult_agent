from uuid import uuid4

from app.schemas import RequestContext


class MockReportSystemConnector:
    def __init__(self) -> None:
        self._records: dict[str, dict] = {}

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
