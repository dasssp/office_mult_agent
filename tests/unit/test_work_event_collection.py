import pytest

from app.connectors.mocks.email import MockEmailConnector
from app.connectors.mocks.enterprise import MockGitLabConnector, MockTaskConnector
from app.domain import MeetingMinutesService, ReportService
from app.schemas import RequestContext
from app.schemas.workflows import SourceType, TranscriptSegment
from app.services.audit import AuditService
from app.services.permissions import PermissionService
from app.services.work_events import MultiSourceWorkEventCollector


def _context() -> RequestContext:
    return RequestContext(
        thread_id="multi-source-report",
        tenant_id="tenant-a",
        operator_id="operator-a",
        employee_id="employee-a",
        permission_scopes={"meeting:review"},
    )


@pytest.mark.asyncio
async def test_collects_gitlab_tasks_email_and_approved_minutes() -> None:
    context = _context()
    meetings = MeetingMinutesService()
    await meetings.generate(
        meeting_id="meeting-1",
        title="项目交付会",
        meeting_date="2026-07-28",
        segments=[
            TranscriptSegment(
                segment_id="segment-1",
                text="确认本周完成发布并同步客户。",
                confidence=0.96,
            )
        ],
        context=context,
    )
    await meetings.review(
        meeting_id="meeting-1",
        approved=True,
        comment=None,
        context=context,
        permissions=PermissionService(),
        audit=AuditService(),
    )

    collection = await MultiSourceWorkEventCollector(
        gitlab=MockGitLabConnector(),
        tasks=MockTaskConnector(),
        email=MockEmailConnector(),
        meeting_minutes=meetings,
    ).collect(
        date_from="2026-07-28",
        date_to="2026-07-28",
        context=context,
    )

    assert collection.source_counts == {
        "gitlab": 1,
        "task": 1,
        "email": 1,
        "meeting": 1,
    }
    assert {event.source_type for event in collection.events} == {
        SourceType.GITLAB,
        SourceType.TASK,
        SourceType.EMAIL,
        SourceType.MEETING,
    }
    draft = await ReportService().generate_daily(
        report_date="2026-07-28",
        events=collection.events,
        source_warnings=collection.source_warnings,
        context=context,
    )
    assert any("邮件协作" in item for item in draft.completed)
    assert any("会议协作" in item and "确认本周完成发布" in item for item in draft.completed)


class _UnavailableEmailConnector(MockEmailConnector):
    async def list_activity(
        self,
        *,
        employee_id: str,
        date_from: str,
        date_to: str,
        context: RequestContext,
    ) -> list[dict]:
        raise RuntimeError("provider unavailable")


class _SensitiveEmailConnector(MockEmailConnector):
    async def list_activity(
        self,
        *,
        employee_id: str,
        date_from: str,
        date_to: str,
        context: RequestContext,
    ) -> list[dict]:
        return [
            {
                "message_id": "email-sensitive",
                "subject": "环境配置",
                "summary": "api_key=do-not-copy-to-report",
                "direction": "sent",
            }
        ]


@pytest.mark.asyncio
async def test_source_failure_keeps_partial_report_events() -> None:
    collection = await MultiSourceWorkEventCollector(
        gitlab=MockGitLabConnector(),
        tasks=MockTaskConnector(),
        email=_UnavailableEmailConnector(),
        meeting_minutes=MeetingMinutesService(),
    ).collect(
        date_from="2026-07-28",
        date_to="2026-07-28",
        context=_context(),
    )

    assert collection.source_counts["email"] == 0
    assert collection.source_counts["gitlab"] == 1
    assert collection.source_counts["task"] == 1
    assert collection.source_warnings == ["email 数据源暂不可用，日报已使用其他来源继续生成。"]


@pytest.mark.asyncio
async def test_sensitive_email_is_excluded_from_report_events() -> None:
    collection = await MultiSourceWorkEventCollector(
        gitlab=MockGitLabConnector(),
        tasks=MockTaskConnector(),
        email=_SensitiveEmailConnector(),
        meeting_minutes=MeetingMinutesService(),
    ).collect(
        date_from="2026-07-28",
        date_to="2026-07-28",
        context=_context(),
    )

    assert collection.source_counts["email"] == 0
    assert collection.source_warnings == ["已忽略 1 条包含敏感标记的邮件活动。"]
