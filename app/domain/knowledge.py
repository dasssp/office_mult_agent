from app.connectors.base import KnowledgeConnector
from app.connectors.mocks.knowledge import MockKnowledgeConnector
from app.schemas import RequestContext
from app.schemas.workflows import KnowledgeAnswer
from app.security import SsoTokenProvider


class KnowledgeService:
    """调用 Java RAG MCP，并对带引用回答执行边界校验。"""

    def __init__(
        self,
        connector: KnowledgeConnector | None = None,
        *,
        token_provider: SsoTokenProvider | None = None,
    ) -> None:
        self._connector = connector or MockKnowledgeConnector()
        self._token_provider = token_provider

    async def answer(self, *, query: str, context: RequestContext) -> KnowledgeAnswer:
        # Authenticate before consulting Redis so cache hits cannot bypass SSO.
        if self._token_provider is not None:
            await self._token_provider.get_access_token(context)
        response = await self._connector.answer(query=query, context=context)
        citations = response.get("citations", [])
        if not citations:
            return KnowledgeAnswer(
                answer="知识库未返回可验证的引用，本次不生成答案。",
                citations=[],
                warnings=["知识库结果缺少引用"],
                status="insufficient_evidence",
            )
        return KnowledgeAnswer.model_validate(
            {
                "answer": response["answer"],
                "citations": citations,
                "status": "completed",
            }
        )
