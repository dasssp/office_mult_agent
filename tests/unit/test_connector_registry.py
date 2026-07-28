import pytest

from app.connectors.registry import ConnectorRegistry, ConnectorUnavailableError
from app.schemas import RequestContext


@pytest.mark.asyncio
async def test_production_registry_never_falls_back_to_mock_writes() -> None:
    registry = ConnectorRegistry.for_environment("production")
    context = RequestContext(
        thread_id="connector-1",
        tenant_id="tenant-a",
        operator_id="operator-a",
    )
    with pytest.raises(ConnectorUnavailableError):
        await registry.report_system.submit_report(
            report={},
            idempotency_key="key-1",
            context=context,
        )
    with pytest.raises(ConnectorUnavailableError):
        await registry.email.send_email(
            subject="subject",
            body="body",
            idempotency_key="key-2",
            context=context,
        )
