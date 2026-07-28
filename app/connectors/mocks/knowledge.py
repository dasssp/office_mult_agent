from app.schemas import RequestContext


class MockKnowledgeConnector:
    """Development-only stand-in for the Java RAG MCP adapter."""

    async def answer(self, *, query: str, context: RequestContext) -> dict:
        return {
            "answer": f"Mock knowledge answer for: {query}",
            "citations": [
                {"document_id": "mock-policy-1", "chunk_id": "section-1", "title": "Mock policy"}
            ],
        }
