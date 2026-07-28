from typing import Any

from mcp.server.fastmcp import FastMCP

from knowledge_mcp_adapter.identity import MockTrustedIdentityProvider
from knowledge_mcp_adapter.tools.knowledge import (
    MockJavaRagClient,
    knowledge_answer,
    knowledge_document_chunk,
    knowledge_document_metadata,
    knowledge_search,
)

mcp = FastMCP("knowledge-mcp-adapter", stateless_http=True, json_response=True)
_client = MockJavaRagClient()
_identity_provider = MockTrustedIdentityProvider()


def _identity():
    """Replace only with identity read from verified gateway request context."""
    return _identity_provider.get_identity()


@mcp.tool()
async def knowledge_answer_tool(query: str) -> dict[str, Any]:
    """Answer with Java RAG and citations. Identity is injected by trusted infrastructure."""
    return await knowledge_answer(query, _identity(), _client)


@mcp.tool()
async def knowledge_search_tool(query: str) -> dict[str, Any]:
    """Search the Java RAG index without exposing identity as an LLM parameter."""
    return await knowledge_search(query, _identity(), _client)


@mcp.tool()
async def knowledge_document_chunk_tool(document_id: str, chunk_id: str) -> dict[str, Any]:
    """Fetch one cited document chunk from Java RAG."""
    return await knowledge_document_chunk(document_id, chunk_id, _identity(), _client)


@mcp.tool()
async def knowledge_document_metadata_tool(document_id: str) -> dict[str, Any]:
    """Fetch metadata for one cited document from Java RAG."""
    return await knowledge_document_metadata(document_id, _identity(), _client)


if __name__ == "__main__":
    mcp.run(transport="streamable-http")
