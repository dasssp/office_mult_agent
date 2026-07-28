import pytest
from knowledge_mcp_adapter.identity import TrustedIdentity
from knowledge_mcp_adapter.tools.knowledge import (
    MockJavaRagClient,
    knowledge_answer,
    knowledge_document_chunk,
    knowledge_document_metadata,
    knowledge_search,
)


@pytest.mark.asyncio
async def test_mock_rag_requires_identity_and_returns_citations() -> None:
    identity = TrustedIdentity("tenant-a", "employee-a")
    result = await knowledge_answer("what is the policy", identity, MockJavaRagClient())
    assert result["citations"][0]["chunk_id"] == "chunk-1"
    with pytest.raises(PermissionError):
        await knowledge_answer("x", TrustedIdentity("", "employee-a"), MockJavaRagClient())


@pytest.mark.asyncio
async def test_mock_rag_supports_search_and_document_tools() -> None:
    identity = TrustedIdentity("tenant-a", "employee-a")
    client = MockJavaRagClient()
    search = await knowledge_search("benefits", identity, client)
    chunk = await knowledge_document_chunk("mock-1", "chunk-1", identity, client)
    metadata = await knowledge_document_metadata("mock-1", identity, client)
    assert search["results"][0]["document_id"] == "mock-1"
    assert chunk["chunk_id"] == "chunk-1"
    assert metadata["title"] == "Mock document"
