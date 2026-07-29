import pytest

from app.domain import KnowledgeService
from app.schemas import RequestContext


@pytest.mark.asyncio
async def test_knowledge_agent_returns_citations_from_rag() -> None:
    context = RequestContext(
        thread_id="knowledge-1",
        tenant_id="tenant-a",
        operator_id="operator-a",
    )
    result = await KnowledgeService().answer(query="leave policy", context=context)
    assert result.status == "completed"
    assert result.citations[0].chunk_id == "section-1"
