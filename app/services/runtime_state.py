from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal
from uuid import uuid4

from app.schemas import RequestContext


@dataclass(frozen=True)
class ConfirmedMemory:
    memory_id: str
    tenant_id: str
    operator_id: str
    key: str
    value: str
    confirmed_at: datetime


@dataclass
class MemoryService:
    _items: dict[tuple[str, str, str], ConfirmedMemory] = field(default_factory=dict)

    def remember(
        self, *, key: str, value: str, confirmed: bool, context: RequestContext
    ) -> ConfirmedMemory:
        if not confirmed:
            raise PermissionError("memory requires explicit user confirmation")
        item = ConfirmedMemory(
            memory_id=str(uuid4()),
            tenant_id=context.tenant_id,
            operator_id=context.operator_id,
            key=key,
            value=value,
            confirmed_at=datetime.now().astimezone(),
        )
        self._items[(context.tenant_id, context.operator_id, key)] = item
        return item

    def list_for(self, context: RequestContext) -> list[ConfirmedMemory]:
        return [
            item
            for (tenant, operator, _), item in self._items.items()
            if tenant == context.tenant_id and operator == context.operator_id
        ]


TaskStatus = Literal["queued", "running", "succeeded", "failed", "cancelled"]


@dataclass
class BackgroundTask:
    task_id: str
    tenant_id: str
    kind: str
    status: TaskStatus = "queued"
    progress: int = 0
    error_code: str | None = None


@dataclass
class BackgroundTaskService:
    _tasks: dict[tuple[str, str], BackgroundTask] = field(default_factory=dict)

    def create(self, *, kind: str, context: RequestContext) -> BackgroundTask:
        task = BackgroundTask(task_id=str(uuid4()), tenant_id=context.tenant_id, kind=kind)
        self._tasks[(context.tenant_id, task.task_id)] = task
        return task

    def update(
        self,
        *,
        task_id: str,
        status: TaskStatus,
        progress: int,
        context: RequestContext,
        error_code: str | None = None,
    ) -> BackgroundTask:
        task = self.get(task_id, context)
        if not 0 <= progress <= 100:
            raise ValueError("progress must be between 0 and 100")
        task.status = status
        task.progress = progress
        task.error_code = error_code
        return task

    def get(self, task_id: str, context: RequestContext) -> BackgroundTask:
        task = self._tasks.get((context.tenant_id, task_id))
        if task is None:
            raise KeyError(task_id)
        return task


@dataclass(frozen=True)
class Schedule:
    schedule_id: str
    tenant_id: str
    name: str
    cron: str
    task_type: str
    enabled: bool = True


@dataclass
class ScheduleService:
    _schedules: dict[tuple[str, str], Schedule] = field(default_factory=dict)

    def create(
        self,
        *,
        name: str,
        cron: str,
        task_type: str,
        context: RequestContext,
    ) -> Schedule:
        if len(cron.split()) != 5:
            raise ValueError("cron expression must contain five fields")
        schedule = Schedule(
            schedule_id=str(uuid4()),
            tenant_id=context.tenant_id,
            name=name,
            cron=cron,
            task_type=task_type,
        )
        self._schedules[(context.tenant_id, schedule.schedule_id)] = schedule
        return schedule

    def list_for(self, context: RequestContext) -> list[Schedule]:
        return [
            schedule
            for (tenant, _), schedule in self._schedules.items()
            if tenant == context.tenant_id
        ]
