from typing import Any

import pytest
from langchain_core.messages import ToolMessage

from app.connectors.mcp_knowledge import McpKnowledgeConnector
from app.domain import KnowledgeService
from app.schemas import RequestContext
from app.security import (
    RequestSsoTokenProvider,
    SsoTokenUnavailableError,
    bind_sso_access_token,
)


class FakeTool:
    name = "knowledge_answer_tool"

    def __init__(self) -> None:
        self.invocation: dict[str, Any] | None = None

    async def ainvoke(self, invocation: dict[str, Any]) -> ToolMessage:
        self.invocation = invocation
        return ToolMessage(
            content=[],
            tool_call_id=invocation["id"],
            artifact={
                "structured_content": {
                    "answer": "年假按制度执行。",
                    "citations": [
                        {
                            "document_id": "policy-1",
                            "chunk_id": "leave-2",
                            "title": "休假制度",
                        }
                    ],
                }
            },
        )


class FakeClient:
    def __init__(self, tool: FakeTool) -> None:
        self.tool = tool

    async def get_tools(self, *, server_name: str | None = None) -> list[FakeTool]:
        assert server_name == "java-rag"
        return [self.tool]


@pytest.mark.asyncio
async def test_connector_forwards_token_only_in_transport_headers() -> None:
    captured_connections: dict[str, Any] = {}
    tool = FakeTool()

    def factory(connections: dict[str, Any]) -> FakeClient:
        captured_connections.update(connections)
        return FakeClient(tool)

    connector = McpKnowledgeConnector(
        "http://localhost:8000/mcp",
        client_factory=factory,
    )
    context = RequestContext(
        thread_id="knowledge-1",
        tenant_id="tenant-a",
        operator_id="operator-a",
    )

    with bind_sso_access_token("delegated-sso-token"):
        result = await connector.answer(query="年假怎么休？", context=context)

    assert result["citations"][0]["document_id"] == "policy-1"
    assert captured_connections["java-rag"]["transport"] == "streamable_http"
    assert captured_connections["java-rag"]["url"] == "http://localhost:8000/mcp"
    assert captured_connections["java-rag"]["headers"]["Authorization"] == (
        "Bearer delegated-sso-token"
    )
    assert tool.invocation is not None
    assert tool.invocation["args"] == {"query": "年假怎么休？"}
    assert "token" not in str(tool.invocation).lower()


@pytest.mark.asyncio
async def test_request_token_is_removed_after_request_scope() -> None:
    provider = RequestSsoTokenProvider()
    context = RequestContext(
        thread_id="knowledge-2",
        tenant_id="tenant-a",
        operator_id="operator-a",
    )
    with bind_sso_access_token("temporary-token"):
        assert await provider.get_access_token(context) == "temporary-token"

    with pytest.raises(SsoTokenUnavailableError):
        await provider.get_access_token(context)


@pytest.mark.asyncio
async def test_knowledge_service_requires_sso_before_cache_or_connector() -> None:
    class ConnectorThatMustNotRun:
        async def answer(self, **_: Any) -> dict[str, Any]:
            raise AssertionError("connector/cache must not run without an SSO token")

    context = RequestContext(
        thread_id="knowledge-3",
        tenant_id="tenant-a",
        operator_id="operator-a",
    )
    service = KnowledgeService(
        ConnectorThatMustNotRun(),
        token_provider=RequestSsoTokenProvider(),
    )

    with pytest.raises(SsoTokenUnavailableError):
        await service.answer(query="机密制度", context=context)
