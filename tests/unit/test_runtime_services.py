import pytest

from app.schemas import RequestContext
from app.services.idempotency import IdempotencyService
from app.services.runtime_state import BackgroundTaskService, MemoryService, ScheduleService
from app.services.sensitive_data import SensitiveDataError, SensitiveDataService


def _context(tenant: str = "tenant-a") -> RequestContext:
    return RequestContext(thread_id="t1", tenant_id=tenant, operator_id="operator-a")


def test_idempotency_results_are_tenant_scoped() -> None:
    service: IdempotencyService[str] = IdempotencyService()
    service.remember("submit-1", "done", _context())
    assert service.get("submit-1", _context()) == "done"
    assert service.get("submit-1", _context("tenant-b")) is None


def test_sensitive_data_guard_blocks_external_sharing() -> None:
    service = SensitiveDataService()
    with pytest.raises(SensitiveDataError):
        service.require_shareable("api_key=secret-value")
    service.require_shareable("ordinary meeting summary")


def test_memory_requires_confirmation_and_is_user_scoped() -> None:
    service = MemoryService()
    with pytest.raises(PermissionError):
        service.remember(key="style", value="concise", confirmed=False, context=_context())
    service.remember(key="style", value="concise", confirmed=True, context=_context())
    assert service.list_for(_context())[0].value == "concise"
    assert service.list_for(_context("tenant-b")) == []


def test_background_task_progress_and_tenant_isolation() -> None:
    service = BackgroundTaskService()
    task = service.create(kind="file_analysis", context=_context())
    updated = service.update(
        task_id=task.task_id,
        status="running",
        progress=25,
        context=_context(),
    )
    assert updated.progress == 25
    with pytest.raises(KeyError):
        service.get(task.task_id, _context("tenant-b"))


def test_schedule_is_validated_and_tenant_scoped() -> None:
    service = ScheduleService()
    service.create(
        name="weekday report",
        cron="0 18 * * 1-5",
        task_type="daily_report",
        context=_context(),
    )
    assert len(service.list_for(_context())) == 1
    assert service.list_for(_context("tenant-b")) == []
    with pytest.raises(ValueError):
        service.create(name="invalid", cron="every day", task_type="report", context=_context())
