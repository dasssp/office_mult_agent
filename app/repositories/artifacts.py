from sqlalchemy.ext.asyncio import async_sessionmaker

from app.models import ArtifactRecord
from app.schemas import RequestContext


class SqlAlchemyArtifactRepository:
    def __init__(self, session_factory: async_sessionmaker) -> None:
        self._session_factory = session_factory

    async def save(
        self,
        *,
        artifact_id: str,
        kind: str,
        object_ref: str,
        sha256: str,
        context: RequestContext,
    ) -> None:
        async with self._session_factory() as session:
            session.add(
                ArtifactRecord(
                    id=artifact_id,
                    tenant_id=context.tenant_id,
                    created_by=context.operator_id,
                    kind=kind,
                    object_ref=object_ref,
                    sha256=sha256,
                    status="available",
                )
            )
            await session.commit()
