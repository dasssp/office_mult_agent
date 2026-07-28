from fastapi.testclient import TestClient

from app.main import app


def test_report_approval_interrupt_can_be_resumed() -> None:
    client = TestClient(app)
    thread_id = "hitl-report-1"
    interrupted = client.post(
        "/assistant/invoke",
        json={
            "thread_id": thread_id,
            "message": "generate daily report",
            "require_approval": True,
            "task_input": {
                "report_date": "2026-07-28",
                "events": [{"event_id": "e1", "title": "Completed work", "status": "completed"}],
            },
        },
    )
    assert interrupted.status_code == 200
    assert interrupted.json()["awaiting_approval"] is True
    headers = {"x-permission-scopes": "report:review"}
    state = client.get(f"/assistant/{thread_id}/state", headers=headers)
    assert state.json()["awaiting_approval"] is True
    resumed = client.post(
        f"/assistant/{thread_id}/resume",
        json={"approved": True, "comment": "looks good"},
        headers=headers,
    )
    assert resumed.status_code == 200
    assert resumed.json()["status"] == "approved"
