from typing import Any, Protocol

from knowledge_mcp_adapter.identity import TrustedIdentity


class JavaRagPort(Protocol):
    async def answer(self, query: str, identity: TrustedIdentity) -> dict[str, Any]: ...
    async def search(self, query: str, identity: TrustedIdentity) -> dict[str, Any]: ...
    async def document_chunk(self, document_id: str, chunk_id: str, identity: TrustedIdentity) -> dict[str, Any]: ...
    async def document_metadata(self, document_id: str, identity: TrustedIdentity) -> dict[str, Any]: ...


class MockJavaRagClient:
    """Development-only data source; it does not represent a live Java RAG connection."""

    async def answer(self, query: str, identity: TrustedIdentity) -> dict[str, Any]:
        identity.as_headers()
        return {"answer": f"Mock answer: {query}", "citations": [{"document_id": "mock-1", "chunk_id": "chunk-1"}]}

    async def search(self, query: str, identity: TrustedIdentity) -> dict[str, Any]:
        identity.as_headers()
        return {"results": [{"document_id": "mock-1", "title": f"Mock match: {query}"}]}

    async def document_chunk(self, document_id: str, chunk_id: str, identity: TrustedIdentity) -> dict[str, Any]:
        identity.as_headers()
        return {"document_id": document_id, "chunk_id": chunk_id, "text": "Mock chunk"}

    async def document_metadata(self, document_id: str, identity: TrustedIdentity) -> dict[str, Any]:
        identity.as_headers()
        return {"document_id": document_id, "title": "Mock document"}


async def knowledge_answer(query: str, identity: TrustedIdentity, client: JavaRagPort) -> dict[str, Any]:
    return await client.answer(query, identity)


async def knowledge_search(query: str, identity: TrustedIdentity, client: JavaRagPort) -> dict[str, Any]:
    return await client.search(query, identity)


async def knowledge_document_chunk(document_id: str, chunk_id: str, identity: TrustedIdentity, client: JavaRagPort) -> dict[str, Any]:
    return await client.document_chunk(document_id, chunk_id, identity)


async def knowledge_document_metadata(document_id: str, identity: TrustedIdentity, client: JavaRagPort) -> dict[str, Any]:
    return await client.document_metadata(document_id, identity)
