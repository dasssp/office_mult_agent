import pytest

from app.schemas import RequestContext
from app.services.approvals import ApprovalService


@pytest.mark.asyncio
async def test_approval_is_tenant_scoped_and_single_use() -> None:
    service = ApprovalService()
    first = RequestContext(
        thread_id="thread-1",
        tenant_id="tenant-a",
        operator_id="reviewer-a",
    )
    other = first.model_copy(update={"tenant_id": "tenant-b"})

    await service.request(target_type="assistant_thread", target_id="thread-1", context=first)
    with pytest.raises(KeyError):
        await service.require_pending(
            target_type="assistant_thread", target_id="thread-1", context=other
        )

    decision = await service.decide(
        target_type="assistant_thread",
        target_id="thread-1",
        approved=True,
        comment="approved",
        context=first,
    )
    assert decision.status == "approved"
    with pytest.raises(KeyError):
        await service.require_pending(
            target_type="assistant_thread", target_id="thread-1", context=first
        )
