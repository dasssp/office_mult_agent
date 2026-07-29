import asyncio
import json
from collections.abc import Callable
from typing import Any, Protocol
from uuid import uuid4

from langchain_core.messages import ToolMessage
from langchain_mcp_adapters.client import MultiServerMCPClient

from app.schemas import RequestContext
from app.security import RequestSsoTokenProvider, SsoTokenProvider


class KnowledgeMcpError(RuntimeError):
    """A sanitized Java RAG MCP integration error."""


class McpClientProtocol(Protocol):
    async def get_tools(self, *, server_name: str | None = None) -> list[Any]: ...


class McpKnowledgeConnector:
    """LangChain MCP client for the Java RAG server."""

    def __init__(
        self,
        url: str,
        *,
        token_provider: SsoTokenProvider | None = None,
        answer_tool_name: str = "knowledge_answer_tool",
        timeout_seconds: float = 15,
        client_factory: Callable[[dict[str, Any]], McpClientProtocol] | None = None,
    ) -> None:
        self._url = url
        self._token_provider = token_provider or RequestSsoTokenProvider()
        self._answer_tool_name = answer_tool_name
        self._timeout_seconds = timeout_seconds
        self._client_factory = client_factory or self._create_client

    @staticmethod
    def _create_client(connections: dict[str, Any]) -> McpClientProtocol:
        return MultiServerMCPClient(connections, handle_tool_errors=False)

    async def answer(self, *, query: str, context: RequestContext) -> dict[str, Any]:
        token = await self._token_provider.get_access_token(context)
        connections = {
            "java-rag": {
                "transport": "streamable_http",
                "url": self._url,
                "headers": {
                    "Authorization": f"Bearer {token}",
                    "X-Request-ID": str(context.request_id),
                },
            }
        }
        try:
            client = self._client_factory(connections)
            tools = await asyncio.wait_for(
                client.get_tools(server_name="java-rag"),
                timeout=self._timeout_seconds,
            )
            tool = next(
                (candidate for candidate in tools if candidate.name == self._answer_tool_name),
                None,
            )
            if tool is None:
                raise KnowledgeMcpError("knowledge_mcp_tool_not_found")
            result = await asyncio.wait_for(
                tool.ainvoke(
                    {
                        "type": "tool_call",
                        "name": tool.name,
                        "id": f"knowledge-{uuid4()}",
                        "args": {"query": query},
                    }
                ),
                timeout=self._timeout_seconds,
            )
        except KnowledgeMcpError:
            raise
        except TimeoutError as error:
            raise KnowledgeMcpError("knowledge_mcp_timeout") from error
        except Exception as error:
            raise KnowledgeMcpError("knowledge_mcp_unavailable") from error
        return self._extract_structured_result(result)

    @staticmethod
    def _extract_structured_result(result: Any) -> dict[str, Any]:
        if isinstance(result, ToolMessage):
            artifact = result.artifact
            if isinstance(artifact, dict):
                structured = artifact.get("structured_content")
                if isinstance(structured, dict):
                    return structured
            result = result.content
        if isinstance(result, dict):
            return result
        if isinstance(result, str):
            try:
                parsed = json.loads(result)
            except json.JSONDecodeError as error:
                raise KnowledgeMcpError("knowledge_mcp_invalid_response") from error
            if isinstance(parsed, dict):
                return parsed
        if isinstance(result, list):
            for block in result:
                if isinstance(block, dict) and isinstance(block.get("text"), str):
                    try:
                        parsed = json.loads(block["text"])
                    except json.JSONDecodeError:
                        continue
                    if isinstance(parsed, dict):
                        return parsed
        raise KnowledgeMcpError("knowledge_mcp_invalid_response")
