from pathlib import Path

import pytest
from sqlalchemy import select

from app.models import AuditLog, Base
from app.repositories.persistence import SqlAlchemyAuditRepository, SqlAlchemyReportRepository
from app.schemas import RequestContext
from app.schemas.workflows import ReportDraft


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
    async with database.session_factory() as session:
        assert len((await session.execute(select(AuditLog))).scalars().all()) == 1
    await database.dispose()
