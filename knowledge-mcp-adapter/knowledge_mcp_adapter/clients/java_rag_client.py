from typing import Any

import httpx

from knowledge_mcp_adapter.identity import TrustedIdentity


class JavaRagClient:
    """Thin async client for the existing Java RAG REST API."""

    def __init__(self, base_url: str, client: httpx.AsyncClient | None = None) -> None:
        self.base_url = base_url.rstrip("/")
        self.client = client or httpx.AsyncClient(timeout=15)

    async def answer(self, query: str, identity: TrustedIdentity) -> dict[str, Any]:
        return await self._post("/answer", {"query": query}, identity)

    async def search(self, query: str, identity: TrustedIdentity) -> dict[str, Any]:
        return await self._post("/search", {"query": query}, identity)

    async def document_chunk(self, document_id: str, chunk_id: str, identity: TrustedIdentity) -> dict[str, Any]:
        return await self._post("/document/chunk", {"document_id": document_id, "chunk_id": chunk_id}, identity)

    async def document_metadata(self, document_id: str, identity: TrustedIdentity) -> dict[str, Any]:
        return await self._post("/document/metadata", {"document_id": document_id}, identity)

    async def _post(self, path: str, payload: dict[str, str], identity: TrustedIdentity) -> dict[str, Any]:
        try:
            response = await self.client.post(f"{self.base_url}{path}", json=payload, headers=identity.as_headers())
            response.raise_for_status()
            return response.json()
        except httpx.TimeoutException as error:
            raise RuntimeError("java_rag_timeout") from error
        except httpx.HTTPStatusError as error:
            raise RuntimeError("java_rag_http_error") from error
