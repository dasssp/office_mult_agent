import asyncio
from collections.abc import Awaitable, Callable
from typing import Literal, cast

from pydantic import ValidationError

from app.connectors.base import EmailConnector, GitLabConnector, TaskConnector
from app.domain import MeetingMinutesService
from app.schemas import RequestContext
from app.schemas.workflows import (
    EmailActivity,
    MeetingMinutesDraft,
    SourceType,
    WorkEvent,
    WorkEventCollection,
)
from app.services.sensitive_data import SensitiveDataService


class MultiSourceWorkEventCollector:
    """并行聚合只读工作数据，并在单个来源失败时保留部分结果。"""

    def __init__(
        self,
        *,
        gitlab: GitLabConnector,
        tasks: TaskConnector,
        email: EmailConnector,
        meeting_minutes: MeetingMinutesService,
    ) -> None:
        self._gitlab = gitlab
        self._tasks = tasks
        self._email = email
        self._meeting_minutes = meeting_minutes
        self._sensitive_data = SensitiveDataService()

    async def collect(
        self,
        *,
        date_from: str,
        date_to: str,
        context: RequestContext,
    ) -> WorkEventCollection:
        employee_id = context.employee_id or context.operator_id
        results = await asyncio.gather(
            self._safe_collect(
                "gitlab",
                lambda: self._collect_gitlab(
                    employee_id=employee_id,
                    date_from=date_from,
                    date_to=date_to,
                    context=context,
                ),
            ),
            self._safe_collect(
                "task",
                lambda: self._collect_tasks(
                    employee_id=employee_id,
                    context=context,
                ),
            ),
            self._safe_collect(
                "email",
                lambda: self._collect_email(
                    employee_id=employee_id,
                    date_from=date_from,
                    date_to=date_to,
                    context=context,
                ),
            ),
            self._safe_collect(
                "meeting",
                lambda: self._collect_meetings(
                    date_from=date_from,
                    date_to=date_to,
                    context=context,
                ),
            ),
        )
        events: list[WorkEvent] = []
        warnings: list[str] = []
        counts: dict[str, int] = {}
        for source, source_events, source_warnings in results:
            events.extend(source_events)
            warnings.extend(source_warnings)
            counts[source] = len(source_events)
        return WorkEventCollection(
            events=events,
            source_warnings=warnings,
            source_counts=counts,
        )

    @staticmethod
    async def _safe_collect(
        source: str,
        operation: Callable[[], Awaitable[tuple[list[WorkEvent], list[str]]]],
    ) -> tuple[str, list[WorkEvent], list[str]]:
        try:
            events, warnings = await operation()
        except (RuntimeError, TimeoutError, ValueError):
            return source, [], [f"{source} 数据源暂不可用，日报已使用其他来源继续生成。"]
        return source, events, warnings

    async def _collect_gitlab(
        self,
        *,
        employee_id: str,
        date_from: str,
        date_to: str,
        context: RequestContext,
    ) -> tuple[list[WorkEvent], list[str]]:
        activity = await self._gitlab.list_activity(
            employee_id=employee_id,
            date_from=date_from,
            date_to=date_to,
            context=context,
        )
        events = [
            WorkEvent(
                event_id=f"gitlab:{item.get('id', index)}",
                title=str(item.get("title", "GitLab 活动")),
                status="completed",
                event_type="code_change",
                project_id=(
                    str(item["project_id"]) if item.get("project_id") is not None else None
                ),
                source_type=SourceType.GITLAB,
                source_id=str(item.get("id", index)),
                evidence_url=f"connector://gitlab/{item.get('id', index)}",
            )
            for index, item in enumerate(activity)
        ]
        return events, []

    async def _collect_tasks(
        self,
        *,
        employee_id: str,
        context: RequestContext,
    ) -> tuple[list[WorkEvent], list[str]]:
        tasks = await self._tasks.list_tasks(
            employee_id=employee_id,
            context=context,
        )
        events = [
            WorkEvent(
                event_id=f"task:{item.get('task_id', index)}",
                title=str(item.get("title", "任务活动")),
                status=_work_status(item.get("status", "unknown")),
                event_type="task_progress",
                project_id=(
                    str(item["project_id"]) if item.get("project_id") is not None else None
                ),
                source_type=SourceType.TASK,
                source_id=str(item.get("task_id", index)),
                evidence_url=f"connector://task/{item.get('task_id', index)}",
            )
            for index, item in enumerate(tasks)
        ]
        return events, []

    async def _collect_email(
        self,
        *,
        employee_id: str,
        date_from: str,
        date_to: str,
        context: RequestContext,
    ) -> tuple[list[WorkEvent], list[str]]:
        activity = await self._email.list_activity(
            employee_id=employee_id,
            date_from=date_from,
            date_to=date_to,
            context=context,
        )
        events: list[WorkEvent] = []
        invalid_count = 0
        sensitive_count = 0
        for item in activity:
            try:
                parsed = EmailActivity.model_validate(item)
            except ValidationError:
                invalid_count += 1
                continue
            if parsed.sensitive or self._sensitive_data.findings(
                f"{parsed.subject}\n{parsed.summary}"
            ):
                sensitive_count += 1
                continue
            events.append(
                WorkEvent(
                    event_id=f"email:{parsed.message_id}",
                    title=f"邮件协作：{parsed.subject}",
                    description=parsed.summary or None,
                    status="completed",
                    event_type="collaboration",
                    event_time=parsed.occurred_at,
                    source_type=SourceType.EMAIL,
                    source_id=parsed.message_id,
                    evidence_url=f"connector://email/{parsed.message_id}",
                )
            )
        warnings = []
        if invalid_count:
            warnings.append(f"已忽略 {invalid_count} 条格式无效的邮件活动。")
        if sensitive_count:
            warnings.append(f"已忽略 {sensitive_count} 条包含敏感标记的邮件活动。")
        return events, warnings

    async def _collect_meetings(
        self,
        *,
        date_from: str,
        date_to: str,
        context: RequestContext,
    ) -> tuple[list[WorkEvent], list[str]]:
        minutes = await self._meeting_minutes.list_for_report(
            date_from=date_from,
            date_to=date_to,
            context=context,
        )
        events: list[WorkEvent] = []
        sensitive_count = 0
        for item in minutes:
            if self._sensitive_data.findings(f"{item.title}\n{item.summary}"):
                sensitive_count += 1
                continue
            events.append(self._meeting_event(item))
        warnings = (
            [f"已忽略 {sensitive_count} 条包含敏感信息的会议纪要。"] if sensitive_count else []
        )
        return events, warnings

    @staticmethod
    def _meeting_event(minutes: MeetingMinutesDraft) -> WorkEvent:
        decisions = "；".join(item.content for item in minutes.decisions[:3])
        result = decisions or minutes.summary
        return WorkEvent(
            event_id=f"meeting:{minutes.meeting_id}",
            title=f"会议协作：{minutes.title}",
            description=minutes.summary or None,
            result=result or None,
            status="completed",
            event_type="meeting",
            event_time=minutes.generated_at,
            source_type=SourceType.MEETING,
            source_id=minutes.meeting_id,
            evidence_url=f"connector://meeting-minutes/{minutes.meeting_id}",
            participants=minutes.participants,
        )


def _work_status(
    value: object,
) -> Literal["completed", "in_progress", "blocked", "planned", "unknown"]:
    status = str(value)
    aliases = {
        "done": "completed",
        "closed": "completed",
        "doing": "in_progress",
        "open": "planned",
    }
    normalized = aliases.get(status, status)
    if normalized in {"completed", "in_progress", "blocked", "planned", "unknown"}:
        return cast(
            Literal["completed", "in_progress", "blocked", "planned", "unknown"],
            normalized,
        )
    return "unknown"
