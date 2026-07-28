from typing import Any

import httpx
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

from app.schemas import RequestContext


class McpKnowledgeConnector:
    """Streamable HTTP client for the independently deployed Java RAG MCP adapter."""

    def __init__(self, url: str, service_token: str | None = None) -> None:
        self._url = url
        self._service_token = service_token

    async def answer(self, *, query: str, context: RequestContext) -> dict[str, Any]:
        # Identity is runtime metadata, never an LLM-fillable tool argument.
        headers = {
            "x-tenant-id": context.tenant_id,
            "x-employee-id": context.employee_id or context.operator_id,
        }
        if self._service_token:
            headers["authorization"] = f"Bearer {self._service_token}"
        async with (
            httpx.AsyncClient(headers=headers) as http_client,
            streamable_http_client(self._url, http_client=http_client) as (read, write, _),
            ClientSession(read, write) as session,
        ):
            await session.initialize()
            result = await session.call_tool(
                "knowledge_answer_tool",
                {"query": query},
                meta={
                    "tenant_id": context.tenant_id,
                    "employee_id": context.employee_id or context.operator_id,
                    "service_token": self._service_token,
                },
            )
        if result.isError:
            raise RuntimeError("knowledge MCP tool returned an error")
        if result.structuredContent is None:
            raise ValueError("knowledge MCP tool returned no structured content")
        return result.structuredContent
