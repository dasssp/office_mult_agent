from types import SimpleNamespace

from fastapi.testclient import TestClient
from langgraph.types import Command

from app.main import app
from app.schemas import Intent


class _InterruptingRuntime:
    async def ainvoke(self, payload, config, *, context):
        if isinstance(payload, Command):
            return {
                "intent": Intent.DAILY_REPORT,
                "status": "approved",
                "result_message": "报告已审核通过。",
                "warnings": [],
                "result": {"status": "approved"},
            }
        return {
            "__interrupt__": [{"value": "review"}],
            "intent": Intent.DAILY_REPORT,
            "status": "awaiting_approval",
            "result_message": "报告等待审核。",
            "warnings": [],
            "subagent_result": {"status": "draft"},
        }

    async def aget_state(self, config):
        return SimpleNamespace(
            values={
                "intent": Intent.DAILY_REPORT,
                "status": "awaiting_approval",
                "subagent_result": {"status": "draft"},
                "required_scope": "report:review",
                "pending_actions": ["review_report"],
            },
            next=("review_report",),
        )


def test_report_approval_interrupt_can_be_resumed() -> None:
    with TestClient(app) as client:
        app.state.assistant_runtime = _InterruptingRuntime()
        thread_id = "hitl-report-1"
        interrupted = client.post(
            "/assistant/invoke",
            json={
                "thread_id": thread_id,
                "message": "生成日报",
                "require_approval": True,
                "task_input": {
                    "report_date": "2026-07-28",
                    "events": [
                        {
                            "event_id": "e1",
                            "title": "完成工作",
                            "status": "completed",
                        }
                    ],
                },
            },
        )
        assert interrupted.status_code == 200
        assert interrupted.json()["awaiting_approval"] is True

        headers = {"x-permission-scopes": "report:review"}
        state = client.get(f"/assistant/{thread_id}/state", headers=headers)
        assert state.status_code == 200
        assert state.json()["awaiting_approval"] is True

        resumed = client.post(
            f"/assistant/{thread_id}/resume",
            json={"approved": True, "comment": "通过"},
            headers=headers,
        )
        assert resumed.status_code == 200
        assert resumed.json()["status"] == "approved"
