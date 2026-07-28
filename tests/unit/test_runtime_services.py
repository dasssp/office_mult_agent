import pytest

from app.schemas import RequestContext
from app.services.idempotency import IdempotencyService
from app.services.runtime_state import BackgroundTaskService, MemoryService, ScheduleService
from app.services.sensitive_data import SensitiveDataError, SensitiveDataService


def _context(tenant: str = "tenant-a") -> RequestContext:
    return RequestContext(thread_id="t1", tenant_id=tenant, operator_id="operator-a")


@pytest.mark.asyncio
async def test_idempotency_results_are_tenant_scoped() -> None:
    service = IdempotencyService()
    await service.remember(
        operation="report.submit",
        key="submit-1",
        result={"status": "done"},
        context=_context(),
    )
    assert await service.get(
        operation="report.submit", key="submit-1", context=_context()
    ) == {"status": "done"}
    assert (
        await service.get(
            operation="report.submit",
            key="submit-1",
            context=_context("tenant-b"),
        )
        is None
    )


def test_sensitive_data_guard_blocks_external_sharing() -> None:
    service = SensitiveDataService()
    with pytest.raises(SensitiveDataError):
        service.require_shareable("api_key=secret-value")
    service.require_shareable("ordinary meeting summary")


@pytest.mark.asyncio
async def test_memory_requires_confirmation_and_is_user_scoped() -> None:
    service = MemoryService()
    with pytest.raises(PermissionError):
        await service.remember(
            key="style", value="concise", confirmed=False, context=_context()
        )
    await service.remember(
        key="style", value="concise", confirmed=True, context=_context()
    )
    assert (await service.list_for(_context()))[0].value == "concise"
    assert await service.list_for(_context("tenant-b")) == []


@pytest.mark.asyncio
async def test_background_task_progress_and_tenant_isolation() -> None:
    service = BackgroundTaskService()
    task = await service.create(kind="file_analysis", context=_context())
    updated = await service.update(
        task_id=task.task_id,
        status="running",
        progress=25,
        context=_context(),
    )
    assert updated.progress == 25
    with pytest.raises(KeyError):
        await service.get(task.task_id, _context("tenant-b"))


@pytest.mark.asyncio
async def test_schedule_is_validated_and_tenant_scoped() -> None:
    service = ScheduleService()
    await service.create(
        name="weekday report",
        cron="0 18 * * 1-5",
        task_type="daily_report",
        context=_context(),
    )
    assert len(await service.list_for(_context())) == 1
    assert await service.list_for(_context("tenant-b")) == []
    with pytest.raises(ValueError):
        await service.create(
            name="invalid",
            cron="every day",
            task_type="report",
            context=_context(),
        )
