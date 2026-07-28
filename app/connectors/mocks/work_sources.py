from app.schemas.workflows import WorkEvent


class MockWorkSources:
    """Read-only stand-ins for IM, Git and task-system connectors."""

    async def collect_events(self) -> list[WorkEvent]:
        return [
            WorkEvent(event_id="im-001", title="确认日报数据口径", status="completed", evidence_url="mock://im/001"),
            WorkEvent(event_id="git-001", title="实现报工 Connector", status="in_progress", evidence_url="mock://git/001"),
            WorkEvent(event_id="task-001", title="等待权限矩阵", status="blocked", evidence_url="mock://task/001"),
        ]
