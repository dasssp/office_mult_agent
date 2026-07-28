from pathlib import Path

import pytest
from sqlalchemy import select

from app.models import AuditLog, Base
from app.repositories.files import SqlAlchemyFileRepository
from app.repositories.meetings import SqlAlchemyMeetingMinutesRepository
from app.repositories.persistence import SqlAlchemyAuditRepository, SqlAlchemyReportRepository
from app.repositories.runtime import (
    SqlAlchemyIdempotencyRepository,
    SqlAlchemyRuntimeStateRepository,
)
from app.schemas import RequestContext
from app.schemas.workflows import MeetingMinutesDraft, ReportDraft
from app.services.files import FileService
from app.services.idempotency import IdempotencyService
from app.services.runtime_state import BackgroundTaskService, MemoryService, ScheduleService


@pytest.mark.asyncio
async def test_report_and_audit_are_persisted_with_tenant_isolation(tmp_path: Path) -> None:
    from app.database import Database

    database = Database(f"sqlite+aiosqlite:///{tmp_path / 'persistence.db'}")
    async with database.engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    context = RequestContext(thread_id="thread-1", tenant_id="tenant-a", operator_id="operator-a")
    draft = ReportDraft(report_id="report-1", report_date="2026-07-28", completed=[], in_progress=[], risks=[], evidence_event_ids=[], status="draft")
    reports = SqlAlchemyReportRepository(database.session_factory)
    audits = SqlAlchemyAuditRepository(database.session_factory)
    await reports.save(draft, context)
    await audits.record(action="report.generate", context=context, target_id=draft.report_id)
    assert (await reports.get(draft.report_id, context)).report_id == draft.report_id
    other_context = RequestContext(thread_id="thread-2", tenant_id="tenant-b", operator_id="operator-b")
    assert await reports.get(draft.report_id, other_context) is None
    meetings = SqlAlchemyMeetingMinutesRepository(database.session_factory)
    minutes = MeetingMinutesDraft(
        meeting_id="meeting-1",
        title="私密会议",
        summary="内容",
        evidence_segment_ids=["s1"],
        warnings=[],
        status="draft",
    )
    await meetings.save(minutes, context)
    assert await meetings.get("meeting-1", context) is not None
    assert await meetings.get("meeting-1", other_context) is None
    first_idempotency = IdempotencyService(
        SqlAlchemyIdempotencyRepository(database.session_factory)
    )
    await first_idempotency.remember(
        operation="report.submit",
        key="key-1",
        result={"submission_id": "submission-1"},
        context=context,
    )
    restarted_idempotency = IdempotencyService(
        SqlAlchemyIdempotencyRepository(database.session_factory)
    )
    assert await restarted_idempotency.get(
        operation="report.submit", key="key-1", context=context
    ) == {"submission_id": "submission-1"}
    runtime_repository = SqlAlchemyRuntimeStateRepository(database.session_factory)
    memory = MemoryService(runtime_repository)
    await memory.remember(
        key="report-style",
        value="concise",
        confirmed=True,
        context=context,
    )
    assert (await MemoryService(runtime_repository).list_for(context))[0].value == "concise"
    tasks = BackgroundTaskService(runtime_repository)
    task = await tasks.create(kind="analysis", context=context)
    assert (await BackgroundTaskService(runtime_repository).get(task.task_id, context)).status == "queued"
    restarted_tasks = BackgroundTaskService(runtime_repository)
    claimed = await restarted_tasks.claim("worker-after-restart")
    assert claimed is not None
    assert claimed.task_id == task.task_id
    assert claimed.attempts == 1
    await restarted_tasks.succeed(claimed, {"rows": 3})
    recovered = await BackgroundTaskService(runtime_repository).get(task.task_id, context)
    assert recovered.status == "succeeded"
    assert recovered.result == {"rows": 3}
    schedules = ScheduleService(runtime_repository)
    await schedules.create(
        name="daily",
        cron="0 18 * * 1-5",
        task_type="daily_report",
        context=context,
    )
    assert len(await ScheduleService(runtime_repository).list_for(context)) == 1
    storage_dir = tmp_path / "uploads"
    files = FileService(
        storage_dir=storage_dir,
        repository=SqlAlchemyFileRepository(database.session_factory),
    )
    file_id = await files.store_and_parse(
        filename="data.csv",
        content=b"name,value\na,1\n",
        content_type="text/csv",
        context=context,
    )
    restarted_files = FileService(
        storage_dir=storage_dir,
        repository=SqlAlchemyFileRepository(database.session_factory),
    )
    assert (await restarted_files.get_rows(file_id, context))[0]["name"] == "a"
    async with database.session_factory() as session:
        assert len((await session.execute(select(AuditLog))).scalars().all()) == 1
    await database.dispose()
