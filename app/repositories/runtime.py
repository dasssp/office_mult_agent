from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.models import (
    BackgroundTaskRecord,
    IdempotencyRecord,
    ScheduleRecord,
    UserMemory,
)
from app.schemas import RequestContext
from app.services.runtime_state import (
    BackgroundTask,
    ConfirmedMemory,
    Schedule,
)


class SqlAlchemyIdempotencyRepository:
    def __init__(self, session_factory: async_sessionmaker) -> None:
        self._session_factory = session_factory

    async def get(
        self, *, operation: str, key: str, context: RequestContext
    ) -> dict[str, object] | None:
        async with self._session_factory() as session:
            result = await session.execute(
                select(IdempotencyRecord).where(
                    IdempotencyRecord.tenant_id == context.tenant_id,
                    IdempotencyRecord.operation == operation,
                    IdempotencyRecord.idempotency_key == key,
                    IdempotencyRecord.status == "completed",
                )
            )
            record = result.scalar_one_or_none()
            return record.result if record is not None else None

    async def save(
        self,
        *,
        operation: str,
        key: str,
        result: dict[str, object],
        context: RequestContext,
    ) -> dict[str, object]:
        async with self._session_factory() as session:
            session.add(
                IdempotencyRecord(
                    tenant_id=context.tenant_id,
                    created_by=context.operator_id,
                    operation=operation,
                    idempotency_key=key,
                    status="completed",
                    result=result,
                )
            )
            try:
                await session.commit()
                return result
            except IntegrityError:
                await session.rollback()
        existing = await self.get(operation=operation, key=key, context=context)
        if existing is None:
            raise RuntimeError("idempotency record conflict without completed result")
        return existing


class SqlAlchemyRuntimeStateRepository:
    def __init__(self, session_factory: async_sessionmaker) -> None:
        self._session_factory = session_factory

    async def save_memory(
        self, item: ConfirmedMemory, context: RequestContext
    ) -> ConfirmedMemory:
        async with self._session_factory() as session:
            result = await session.execute(
                select(UserMemory).where(
                    UserMemory.tenant_id == context.tenant_id,
                    UserMemory.created_by == context.operator_id,
                    UserMemory.memory_key == item.key,
                )
            )
            record = result.scalar_one_or_none()
            if record is None:
                session.add(
                    UserMemory(
                        id=item.memory_id,
                        tenant_id=context.tenant_id,
                        created_by=context.operator_id,
                        memory_key=item.key,
                        memory_value=item.value,
                        confirmed=True,
                    )
                )
            else:
                record.memory_value = item.value
                record.confirmed = True
                record.version += 1
            await session.commit()
        return item

    async def list_memories(self, context: RequestContext) -> list[ConfirmedMemory]:
        async with self._session_factory() as session:
            result = await session.execute(
                select(UserMemory).where(
                    UserMemory.tenant_id == context.tenant_id,
                    UserMemory.created_by == context.operator_id,
                    UserMemory.confirmed.is_(True),
                )
            )
            return [
                ConfirmedMemory(
                    memory_id=row.id,
                    tenant_id=row.tenant_id,
                    operator_id=row.created_by,
                    key=row.memory_key,
                    value=row.memory_value,
                    confirmed_at=row.updated_at,
                )
                for row in result.scalars()
            ]

    async def save_task(
        self, task: BackgroundTask, context: RequestContext
    ) -> BackgroundTask:
        async with self._session_factory() as session:
            record = await session.get(BackgroundTaskRecord, task.task_id)
            if record is None:
                session.add(
                    BackgroundTaskRecord(
                        id=task.task_id,
                        tenant_id=context.tenant_id,
                        created_by=context.operator_id,
                        kind=task.kind,
                        status=task.status,
                        progress=task.progress,
                        error_code=task.error_code,
                    )
                )
            elif record.tenant_id != context.tenant_id:
                raise KeyError(task.task_id)
            else:
                record.status = task.status
                record.progress = task.progress
                record.error_code = task.error_code
                record.version += 1
            await session.commit()
        return task

    async def get_task(
        self, task_id: str, context: RequestContext
    ) -> BackgroundTask | None:
        async with self._session_factory() as session:
            result = await session.execute(
                select(BackgroundTaskRecord).where(
                    BackgroundTaskRecord.id == task_id,
                    BackgroundTaskRecord.tenant_id == context.tenant_id,
                )
            )
            row = result.scalar_one_or_none()
            return (
                BackgroundTask(
                    task_id=row.id,
                    tenant_id=row.tenant_id,
                    kind=row.kind,
                    status=row.status,  # type: ignore[arg-type]
                    progress=row.progress,
                    error_code=row.error_code,
                )
                if row is not None
                else None
            )

    async def save_schedule(
        self, schedule: Schedule, context: RequestContext
    ) -> Schedule:
        async with self._session_factory() as session:
            session.add(
                ScheduleRecord(
                    id=schedule.schedule_id,
                    tenant_id=context.tenant_id,
                    created_by=context.operator_id,
                    name=schedule.name,
                    cron=schedule.cron,
                    task_type=schedule.task_type,
                    payload={},
                    status="active" if schedule.enabled else "disabled",
                )
            )
            await session.commit()
        return schedule

    async def list_schedules(self, context: RequestContext) -> list[Schedule]:
        async with self._session_factory() as session:
            result = await session.execute(
                select(ScheduleRecord).where(
                    ScheduleRecord.tenant_id == context.tenant_id
                )
            )
            return [
                Schedule(
                    schedule_id=row.id,
                    tenant_id=row.tenant_id,
                    name=row.name,
                    cron=row.cron,
                    task_type=row.task_type,
                    enabled=row.status == "active",
                )
                for row in result.scalars()
            ]
