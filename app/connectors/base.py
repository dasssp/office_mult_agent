from typing import Protocol

from app.schemas import RequestContext


class ReportSystemConnector(Protocol):
    async def submit_report(self, *, report: dict, idempotency_key: str, context: RequestContext) -> dict: ...

    async def get_report_status(self, *, submission_id: str, context: RequestContext) -> dict: ...
