from datetime import datetime, timedelta

from sqlalchemy import and_, or_, select
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
                        payload=task.payload or {},
                        result=task.result,
                        attempts=task.attempts,
                        max_attempts=task.max_attempts,
                        available_at=task.available_at or datetime.now().astimezone(),
                        locked_at=task.locked_at,
                        locked_by=task.locked_by,
                        cancel_requested=task.cancel_requested,
                        finished_at=task.finished_at,
                    )
                )
            elif record.tenant_id != context.tenant_id:
                raise KeyError(task.task_id)
            else:
                record.status = task.status
                record.progress = task.progress
                record.error_code = task.error_code
                record.payload = task.payload or {}
                record.result = task.result
                record.attempts = task.attempts
                record.max_attempts = task.max_attempts
                record.available_at = task.available_at or datetime.now().astimezone()
                record.locked_at = task.locked_at
                record.locked_by = task.locked_by
                record.cancel_requested = task.cancel_requested
                record.finished_at = task.finished_at
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
            return self._to_task(row) if row is not None else None

    async def claim_next_task(
        self, *, worker_id: str, now: datetime, lease_timeout_seconds: int
    ) -> BackgroundTask | None:
        stale_before = now - timedelta(seconds=lease_timeout_seconds)
        async with self._session_factory() as session:
            async with session.begin():
                result = await session.execute(
                    select(BackgroundTaskRecord)
                    .where(
                        or_(
                            and_(
                                BackgroundTaskRecord.status.in_(
                                    ("queued", "retry_wait")
                                ),
                                BackgroundTaskRecord.available_at <= now,
                            ),
                            and_(
                                BackgroundTaskRecord.status == "running",
                                BackgroundTaskRecord.locked_at <= stale_before,
                            ),
                        )
                    )
                    .order_by(
                        BackgroundTaskRecord.available_at,
                        BackgroundTaskRecord.created_at,
                    )
                    .with_for_update(skip_locked=True)
                    .limit(1)
                )
                row = result.scalar_one_or_none()
                if row is None:
                    return None
                if row.cancel_requested:
                    row.status = "cancelled"
                    row.finished_at = now
                    row.version += 1
                    return None
                if row.status == "running" and row.attempts >= row.max_attempts:
                    row.status = "failed"
                    row.error_code = "TASK_LEASE_EXPIRED"
                    row.finished_at = now
                    row.version += 1
                    return None
                row.status = "running"
                row.attempts += 1
                row.progress = max(row.progress, 5)
                row.locked_by = worker_id
                row.locked_at = now
                row.version += 1
            return self._to_task(row)

    async def save_claimed_task(self, task: BackgroundTask) -> BackgroundTask:
        async with self._session_factory() as session:
            async with session.begin():
                result = await session.execute(
                    select(BackgroundTaskRecord)
                    .where(
                        BackgroundTaskRecord.id == task.task_id,
                        BackgroundTaskRecord.tenant_id == task.tenant_id,
                    )
                    .with_for_update()
                )
                row = result.scalar_one_or_none()
                if row is None:
                    raise KeyError(task.task_id)
                row.status = task.status
                row.progress = task.progress
                row.error_code = task.error_code
                row.result = task.result
                row.available_at = task.available_at or datetime.now().astimezone()
                row.locked_at = task.locked_at
                row.locked_by = task.locked_by
                row.cancel_requested = task.cancel_requested
                row.finished_at = task.finished_at
                row.version += 1
            return task

    async def request_task_cancel(
        self, task_id: str, context: RequestContext
    ) -> BackgroundTask | None:
        async with self._session_factory() as session:
            async with session.begin():
                result = await session.execute(
                    select(BackgroundTaskRecord)
                    .where(
                        BackgroundTaskRecord.id == task_id,
                        BackgroundTaskRecord.tenant_id == context.tenant_id,
                    )
                    .with_for_update()
                )
                row = result.scalar_one_or_none()
                if row is None:
                    return None
                row.cancel_requested = True
                if row.status in {"queued", "retry_wait"}:
                    row.status = "cancelled"
                    row.finished_at = datetime.now().astimezone()
                row.version += 1
            return self._to_task(row)

    @staticmethod
    def _to_task(row: BackgroundTaskRecord) -> BackgroundTask:
        return BackgroundTask(
            task_id=row.id,
            tenant_id=row.tenant_id,
            operator_id=row.created_by,
            kind=row.kind,
            status=row.status,  # type: ignore[arg-type]
            progress=row.progress,
            error_code=row.error_code,
            payload=row.payload,
            result=row.result,
            attempts=row.attempts,
            max_attempts=row.max_attempts,
            available_at=row.available_at,
            locked_at=row.locked_at,
            locked_by=row.locked_by,
            cancel_requested=row.cancel_requested,
            finished_at=row.finished_at,
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
