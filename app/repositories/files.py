from pathlib import Path
from typing import Protocol

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.models import FileRecord
from app.schemas import RequestContext


class FileMetadataRecord(Protocol):
    @property
    def file_id(self) -> str: ...

    @property
    def filename(self) -> str: ...

    @property
    def content_type(self) -> str | None: ...

    @property
    def byte_size(self) -> int: ...

    @property
    def sha256(self) -> str: ...

    @property
    def row_count(self) -> int: ...

    @property
    def file_type(self) -> str: ...

    @property
    def storage_ref(self) -> str: ...

    @property
    def tenant_id(self) -> str: ...

    @property
    def created_by(self) -> str: ...

    @property
    def status(self) -> str: ...


class FileRepository(Protocol):
    async def save(
        self, metadata: FileMetadataRecord, context: RequestContext
    ) -> None: ...

    async def get(
        self, file_id: str, context: RequestContext
    ) -> dict[str, object] | None: ...

    async def delete(self, file_id: str, context: RequestContext) -> None: ...


class SqlAlchemyFileRepository:
    def __init__(self, session_factory: async_sessionmaker) -> None:
        self._session_factory = session_factory

    async def save(
        self, metadata: FileMetadataRecord, context: RequestContext
    ) -> None:
        async with self._session_factory() as session:
            session.add(
                FileRecord(
                    id=metadata.file_id,
                    tenant_id=context.tenant_id,
                    created_by=context.operator_id,
                    filename=metadata.filename,
                    content_type=metadata.content_type,
                    byte_size=metadata.byte_size,
                    sha256=metadata.sha256,
                    row_count=metadata.row_count,
                    file_type=metadata.file_type,
                    object_ref=metadata.storage_ref,
                    status=metadata.status,
                )
            )
            await session.commit()

    async def get(
        self, file_id: str, context: RequestContext
    ) -> dict[str, object] | None:
        async with self._session_factory() as session:
            result = await session.execute(
                select(FileRecord).where(
                    FileRecord.id == file_id,
                    FileRecord.tenant_id == context.tenant_id,
                )
            )
            row = result.scalar_one_or_none()
            if row is None or row.object_ref is None:
                return None
            return {
                "file_id": row.id,
                "filename": row.filename,
                "content_type": row.content_type,
                "byte_size": row.byte_size,
                "sha256": row.sha256,
                "row_count": row.row_count,
                "file_type": row.file_type,
                "storage_ref": str(Path(row.object_ref)),
                "tenant_id": row.tenant_id,
                "created_by": row.created_by,
                "status": row.status,
            }

    async def delete(self, file_id: str, context: RequestContext) -> None:
        async with self._session_factory() as session:
            await session.execute(
                delete(FileRecord).where(
                    FileRecord.id == file_id,
                    FileRecord.tenant_id == context.tenant_id,
                )
            )
            await session.commit()
