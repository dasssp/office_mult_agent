from app.connectors.base import KnowledgeConnector
from app.connectors.mocks.knowledge import MockKnowledgeConnector
from app.schemas import RequestContext
from app.schemas.workflows import KnowledgeAnswer
from app.services.permissions import PermissionService


class KnowledgeAgent:
    """Read-only knowledge capability delegated to the Java RAG adapter."""

    def __init__(self, connector: KnowledgeConnector | None = None) -> None:
        self._connector = connector or MockKnowledgeConnector()

    async def answer(
        self, *, query: str, context: RequestContext, permissions: PermissionService
    ) -> KnowledgeAnswer:
        permissions.require(context, "knowledge:read")
        response = await self._connector.answer(query=query, context=context)
        citations = response.get("citations", [])
        if not citations:
            return KnowledgeAnswer(
                answer="No answer is returned without supporting citations.",
                citations=[],
                warnings=["knowledge source returned no citations"],
                status="insufficient_evidence",
            )
        return KnowledgeAnswer.model_validate(
            {"answer": response["answer"], "citations": citations, "status": "completed"}
        )
