from typing import Any

from mcp.server.fastmcp import Context, FastMCP

from knowledge_mcp_adapter.clients.java_rag_client import JavaRagClient
from knowledge_mcp_adapter.config import get_settings
from knowledge_mcp_adapter.identity import TrustedIdentity
from knowledge_mcp_adapter.tools.knowledge import (
    MockJavaRagClient,
    knowledge_answer,
    knowledge_document_chunk,
    knowledge_document_metadata,
    knowledge_search,
)

mcp = FastMCP("knowledge-mcp-adapter", stateless_http=True, json_response=True)
settings = get_settings()
if settings.app_env == "production" and not settings.java_rag_base_url:
    raise RuntimeError("JAVA_RAG_BASE_URL is required in production")
if settings.app_env == "production" and not settings.mcp_service_token:
    raise RuntimeError("MCP_SERVICE_TOKEN is required in production")
_client = (
    JavaRagClient(settings.java_rag_base_url)
    if settings.java_rag_base_url
    else MockJavaRagClient()
)


def _identity(ctx: Context) -> TrustedIdentity:
    meta = ctx.request_context.meta
    trusted = meta.model_extra if meta is not None and meta.model_extra is not None else {}
    if (
        settings.mcp_service_token
        and trusted.get("service_token") != settings.mcp_service_token
    ):
        raise PermissionError("invalid MCP service credential")
    identity = TrustedIdentity(
        tenant_id=str(trusted.get("tenant_id", "")),
        employee_id=str(trusted.get("employee_id", "")),
    )
    identity.as_headers()
    return identity


@mcp.tool()
async def knowledge_answer_tool(query: str, ctx: Context) -> dict[str, Any]:
    """Answer with Java RAG and citations. Identity is injected by trusted infrastructure."""
    return await knowledge_answer(query, _identity(ctx), _client)


@mcp.tool()
async def knowledge_search_tool(query: str, ctx: Context) -> dict[str, Any]:
    """Search the Java RAG index without exposing identity as an LLM parameter."""
    return await knowledge_search(query, _identity(ctx), _client)


@mcp.tool()
async def knowledge_document_chunk_tool(
    document_id: str, chunk_id: str, ctx: Context
) -> dict[str, Any]:
    """Fetch one cited document chunk from Java RAG."""
    return await knowledge_document_chunk(document_id, chunk_id, _identity(ctx), _client)


@mcp.tool()
async def knowledge_document_metadata_tool(
    document_id: str, ctx: Context
) -> dict[str, Any]:
    """Fetch metadata for one cited document from Java RAG."""
    return await knowledge_document_metadata(document_id, _identity(ctx), _client)


if __name__ == "__main__":
    mcp.run(transport="streamable-http")
