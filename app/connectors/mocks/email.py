from uuid import uuid4

from app.schemas import RequestContext


class MockEmailConnector:
    def __init__(self) -> None:
        self._sent: dict[str, dict[str, str]] = {}

    async def list_activity(
        self,
        *,
        employee_id: str,
        date_from: str,
        date_to: str,
        context: RequestContext,
    ) -> list[dict]:
        del employee_id, date_from, date_to
        return [
            {
                "message_id": "email-1",
                "subject": "同步项目交付进展",
                "summary": "已向项目组同步当前进展和后续安排。",
                "direction": "sent",
                "sensitive": False,
            }
        ]

    async def send_email(self, *, subject: str, body: str, idempotency_key: str, context: RequestContext) -> dict[str, str]:
        if idempotency_key not in self._sent:
            self._sent[idempotency_key] = {"message_id": str(uuid4()), "status": "sent", "tenant_id": context.tenant_id}
        return self._sent[idempotency_key]

    async def get_send_status(
        self, *, message_id: str, context: RequestContext
    ) -> dict[str, str]:
        for record in self._sent.values():
            if (
                record["message_id"] == message_id
                and record["tenant_id"] == context.tenant_id
            ):
                return {"message_id": message_id, "status": record["status"]}
        return {"message_id": message_id, "status": "not_found"}
