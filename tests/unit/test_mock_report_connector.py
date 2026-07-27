import pytest

from app.connectors.mocks.report_system import MockReportSystemConnector
from app.schemas import RequestContext


@pytest.mark.asyncio
async def test_report_submission_is_idempotent() -> None:
    connector = MockReportSystemConnector()
    context = RequestContext(thread_id="t1", tenant_id="tenant-a", operator_id="operator-a")
    first = await connector.submit_report(report={"title": "日报"}, idempotency_key="key-1", context=context)
    second = await connector.submit_report(report={"title": "日报"}, idempotency_key="key-1", context=context)
    assert first["submission_id"] == second["submission_id"]
