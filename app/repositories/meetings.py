from typing import Protocol

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.models import MeetingMinutesRecord
from app.schemas import RequestContext
from app.schemas.workflows import MeetingMinutesDraft


class MeetingMinutesRepository(Protocol):
    async def save(
        self, draft: MeetingMinutesDraft, context: RequestContext
    ) -> MeetingMinutesDraft: ...

    async def get(
        self, meeting_id: str, context: RequestContext
    ) -> MeetingMinutesDraft | None: ...


class InMemoryMeetingMinutesRepository:
    def __init__(self) -> None:
        self._drafts: dict[tuple[str, str], MeetingMinutesDraft] = {}

    async def save(
        self, draft: MeetingMinutesDraft, context: RequestContext
    ) -> MeetingMinutesDraft:
        self._drafts[(context.tenant_id, draft.meeting_id)] = draft
        return draft

    async def get(
        self, meeting_id: str, context: RequestContext
    ) -> MeetingMinutesDraft | None:
        return self._drafts.get((context.tenant_id, meeting_id))


class SqlAlchemyMeetingMinutesRepository:
    def __init__(self, session_factory: async_sessionmaker) -> None:
        self._session_factory = session_factory

    async def save(
        self, draft: MeetingMinutesDraft, context: RequestContext
    ) -> MeetingMinutesDraft:
        async with self._session_factory() as session:
            result = await session.execute(
                select(MeetingMinutesRecord).where(
                    MeetingMinutesRecord.tenant_id == context.tenant_id,
                    MeetingMinutesRecord.meeting_id == draft.meeting_id,
                )
            )
            record = result.scalar_one_or_none()
            if record is None:
                session.add(
                    MeetingMinutesRecord(
                        tenant_id=context.tenant_id,
                        created_by=context.operator_id,
                        meeting_id=draft.meeting_id,
                        status=draft.status,
                        payload=draft.model_dump(mode="json"),
                    )
                )
            else:
                record.status = draft.status
                record.payload = draft.model_dump(mode="json")
                record.version += 1
            await session.commit()
        return draft

    async def get(
        self, meeting_id: str, context: RequestContext
    ) -> MeetingMinutesDraft | None:
        async with self._session_factory() as session:
            result = await session.execute(
                select(MeetingMinutesRecord).where(
                    MeetingMinutesRecord.tenant_id == context.tenant_id,
                    MeetingMinutesRecord.meeting_id == meeting_id,
                )
            )
            record = result.scalar_one_or_none()
            return (
                MeetingMinutesDraft.model_validate(record.payload)
                if record is not None
                else None
            )
