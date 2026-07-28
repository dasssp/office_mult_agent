import asyncio
from dataclasses import dataclass
from datetime import datetime, timedelta
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


TaskStatus = Literal[
    "queued",
    "running",
    "retry_wait",
    "succeeded",
    "failed",
    "cancelled",
]


@dataclass
class BackgroundTask:
    task_id: str
    tenant_id: str
    kind: str
    operator_id: str = ""
    status: TaskStatus = "queued"
    progress: int = 0
    error_code: str | None = None
    payload: dict[str, object] | None = None
    result: dict[str, object] | None = None
    attempts: int = 0
    max_attempts: int = 3
    available_at: datetime | None = None
    locked_at: datetime | None = None
    locked_by: str | None = None
    cancel_requested: bool = False
    finished_at: datetime | None = None


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

    async def claim_next_task(
        self, *, worker_id: str, now: datetime, lease_timeout_seconds: int
    ) -> BackgroundTask | None: ...

    async def save_claimed_task(self, task: BackgroundTask) -> BackgroundTask: ...

    async def request_task_cancel(
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
        self._task_lock = asyncio.Lock()

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

    async def claim_next_task(
        self, *, worker_id: str, now: datetime, lease_timeout_seconds: int
    ) -> BackgroundTask | None:
        async with self._task_lock:
            for task in self._tasks.values():
                available_at = task.available_at or now
                stale_running = (
                    task.status == "running"
                    and task.locked_at is not None
                    and task.locked_at
                    <= now - timedelta(seconds=lease_timeout_seconds)
                )
                if (
                    not stale_running
                    and (
                        task.status not in {"queued", "retry_wait"}
                        or available_at > now
                    )
                ):
                    continue
                if task.cancel_requested:
                    task.status = "cancelled"
                    task.finished_at = now
                    continue
                if stale_running and task.attempts >= task.max_attempts:
                    task.status = "failed"
                    task.error_code = "TASK_LEASE_EXPIRED"
                    task.finished_at = now
                    continue
                task.status = "running"
                task.attempts += 1
                task.progress = max(task.progress, 5)
                task.locked_by = worker_id
                task.locked_at = now
                return task
        return None

    async def save_claimed_task(self, task: BackgroundTask) -> BackgroundTask:
        async with self._task_lock:
            key = (task.tenant_id, task.task_id)
            if key not in self._tasks:
                raise KeyError(task.task_id)
            self._tasks[key] = task
            return task

    async def request_task_cancel(
        self, task_id: str, context: RequestContext
    ) -> BackgroundTask | None:
        async with self._task_lock:
            task = self._tasks.get((context.tenant_id, task_id))
            if task is None:
                return None
            task.cancel_requested = True
            if task.status in {"queued", "retry_wait"}:
                task.status = "cancelled"
                task.finished_at = datetime.now().astimezone()
            return task

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

    async def create(
        self,
        *,
        kind: str,
        context: RequestContext,
        payload: dict[str, object] | None = None,
        max_attempts: int = 3,
    ) -> BackgroundTask:
        if max_attempts < 1:
            raise ValueError("max_attempts must be positive")
        task = BackgroundTask(
            task_id=str(uuid4()),
            tenant_id=context.tenant_id,
            operator_id=context.operator_id,
            kind=kind,
            payload=payload or {},
            max_attempts=max_attempts,
            available_at=datetime.now().astimezone(),
        )
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

    async def cancel(
        self, task_id: str, context: RequestContext
    ) -> BackgroundTask:
        task = await self._repository.request_task_cancel(task_id, context)
        if task is None:
            raise KeyError(task_id)
        return task

    async def claim(
        self, worker_id: str, *, lease_timeout_seconds: int = 360
    ) -> BackgroundTask | None:
        return await self._repository.claim_next_task(
            worker_id=worker_id,
            now=datetime.now().astimezone(),
            lease_timeout_seconds=lease_timeout_seconds,
        )

    async def succeed(
        self,
        task: BackgroundTask,
        result: dict[str, object],
    ) -> BackgroundTask:
        task.status = "succeeded"
        task.progress = 100
        task.result = result
        task.error_code = None
        task.locked_at = None
        task.locked_by = None
        task.finished_at = datetime.now().astimezone()
        return await self._repository.save_claimed_task(task)

    async def fail(
        self,
        task: BackgroundTask,
        *,
        error_code: str,
        retry_delay_seconds: int,
    ) -> BackgroundTask:
        task.error_code = error_code
        task.locked_at = None
        task.locked_by = None
        if task.cancel_requested:
            task.status = "cancelled"
            task.finished_at = datetime.now().astimezone()
        elif task.attempts < task.max_attempts:
            task.status = "retry_wait"
            task.available_at = datetime.now().astimezone() + timedelta(
                seconds=max(0, retry_delay_seconds)
            )
        else:
            task.status = "failed"
            task.finished_at = datetime.now().astimezone()
        return await self._repository.save_claimed_task(task)


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
