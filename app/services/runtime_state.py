from dataclasses import dataclass
from datetime import datetime
from typing import Literal, Protocol
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


TaskStatus = Literal["queued", "running", "succeeded", "failed", "cancelled"]


@dataclass
class BackgroundTask:
    task_id: str
    tenant_id: str
    kind: str
    status: TaskStatus = "queued"
    progress: int = 0
    error_code: str | None = None


@dataclass(frozen=True)
class Schedule:
    schedule_id: str
    tenant_id: str
    name: str
    cron: str
    task_type: str
    enabled: bool = True


class RuntimeStateRepository(Protocol):
    async def save_memory(
        self, item: ConfirmedMemory, context: RequestContext
    ) -> ConfirmedMemory: ...

    async def list_memories(self, context: RequestContext) -> list[ConfirmedMemory]: ...

    async def save_task(
        self, task: BackgroundTask, context: RequestContext
    ) -> BackgroundTask: ...

    async def get_task(
        self, task_id: str, context: RequestContext
    ) -> BackgroundTask | None: ...

    async def save_schedule(
        self, schedule: Schedule, context: RequestContext
    ) -> Schedule: ...

    async def list_schedules(self, context: RequestContext) -> list[Schedule]: ...


class InMemoryRuntimeStateRepository:
    def __init__(self) -> None:
        self._memories: dict[tuple[str, str, str], ConfirmedMemory] = {}
        self._tasks: dict[tuple[str, str], BackgroundTask] = {}
        self._schedules: dict[tuple[str, str], Schedule] = {}

    async def save_memory(
        self, item: ConfirmedMemory, context: RequestContext
    ) -> ConfirmedMemory:
        self._memories[(context.tenant_id, context.operator_id, item.key)] = item
        return item

    async def list_memories(self, context: RequestContext) -> list[ConfirmedMemory]:
        return [
            item
            for (tenant, operator, _), item in self._memories.items()
            if tenant == context.tenant_id and operator == context.operator_id
        ]

    async def save_task(
        self, task: BackgroundTask, context: RequestContext
    ) -> BackgroundTask:
        self._tasks[(context.tenant_id, task.task_id)] = task
        return task

    async def get_task(
        self, task_id: str, context: RequestContext
    ) -> BackgroundTask | None:
        return self._tasks.get((context.tenant_id, task_id))

    async def save_schedule(
        self, schedule: Schedule, context: RequestContext
    ) -> Schedule:
        self._schedules[(context.tenant_id, schedule.schedule_id)] = schedule
        return schedule

    async def list_schedules(self, context: RequestContext) -> list[Schedule]:
        return [
            schedule
            for (tenant, _), schedule in self._schedules.items()
            if tenant == context.tenant_id
        ]


class MemoryService:
    def __init__(self, repository: RuntimeStateRepository | None = None) -> None:
        self._repository = repository or InMemoryRuntimeStateRepository()

    async def remember(
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
        return await self._repository.save_memory(item, context)

    async def list_for(self, context: RequestContext) -> list[ConfirmedMemory]:
        return await self._repository.list_memories(context)


class BackgroundTaskService:
    def __init__(self, repository: RuntimeStateRepository | None = None) -> None:
        self._repository = repository or InMemoryRuntimeStateRepository()

    async def create(self, *, kind: str, context: RequestContext) -> BackgroundTask:
        task = BackgroundTask(task_id=str(uuid4()), tenant_id=context.tenant_id, kind=kind)
        return await self._repository.save_task(task, context)

    async def update(
        self,
        *,
        task_id: str,
        status: TaskStatus,
        progress: int,
        context: RequestContext,
        error_code: str | None = None,
    ) -> BackgroundTask:
        task = await self.get(task_id, context)
        if not 0 <= progress <= 100:
            raise ValueError("progress must be between 0 and 100")
        task.status = status
        task.progress = progress
        task.error_code = error_code
        return await self._repository.save_task(task, context)

    async def get(self, task_id: str, context: RequestContext) -> BackgroundTask:
        task = await self._repository.get_task(task_id, context)
        if task is None:
            raise KeyError(task_id)
        return task


class ScheduleService:
    def __init__(self, repository: RuntimeStateRepository | None = None) -> None:
        self._repository = repository or InMemoryRuntimeStateRepository()

    async def create(
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
        return await self._repository.save_schedule(schedule, context)

    async def list_for(self, context: RequestContext) -> list[Schedule]:
        return await self._repository.list_schedules(context)
