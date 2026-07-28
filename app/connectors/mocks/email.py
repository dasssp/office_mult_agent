from uuid import uuid4

from app.schemas import RequestContext


class MockEmailConnector:
    def __init__(self) -> None:
        self._sent: dict[str, dict[str, str]] = {}

    async def send_email(self, *, subject: str, body: str, idempotency_key: str, context: RequestContext) -> dict[str, str]:
        if idempotency_key not in self._sent:
            self._sent[idempotency_key] = {"message_id": str(uuid4()), "status": "sent", "tenant_id": context.tenant_id}
        return self._sent[idempotency_key]
