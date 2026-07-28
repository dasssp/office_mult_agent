from typing import Any

from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

from app.schemas import RequestContext


class McpKnowledgeConnector:
    """Streamable HTTP client for the independently deployed Java RAG MCP adapter."""

    def __init__(self, url: str) -> None:
        self._url = url

    async def answer(self, *, query: str, context: RequestContext) -> dict[str, Any]:
        # Identity is deliberately not exposed as a tool argument. The MCP adapter
        # obtains trusted identity from its own gateway/runtime boundary.
        async with (
            streamable_http_client(self._url) as (read, write, _),
            ClientSession(read, write) as session,
        ):
            await session.initialize()
            result = await session.call_tool(
                "knowledge_answer_tool",
                {"query": query},
            )
        if result.isError:
            raise RuntimeError("knowledge MCP tool returned an error")
        if result.structuredContent is None:
            raise ValueError("knowledge MCP tool returned no structured content")
        return result.structuredContent
