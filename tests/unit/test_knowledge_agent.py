import pytest

from app.agents.knowledge_agent import KnowledgeAgent
from app.schemas import RequestContext
from app.services.permissions import PermissionService


@pytest.mark.asyncio
async def test_knowledge_agent_requires_permission_and_returns_citations() -> None:
    context = RequestContext(
        thread_id="knowledge-1",
        tenant_id="tenant-a",
        operator_id="operator-a",
        permission_scopes={"knowledge:read"},
    )
    result = await KnowledgeAgent().answer(
        query="leave policy", context=context, permissions=PermissionService()
    )
    assert result.status == "completed"
    assert result.citations[0].chunk_id == "section-1"
