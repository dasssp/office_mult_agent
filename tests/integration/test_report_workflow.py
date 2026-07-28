from fastapi.testclient import TestClient

from app.main import app


def test_report_requires_approval_then_submits_idempotently() -> None:
    client = TestClient(app)
    generated = client.post("/reports/generate", json={"report_date": "2026-07-28", "use_mock_sources": True})
    assert generated.status_code == 200
    report_id = generated.json()["report_id"]

    assert client.post(f"/reports/{report_id}/submit").status_code == 403
    assert client.post(f"/reports/{report_id}/review", json={"approved": True}).status_code == 403
    reviewed = client.post(f"/reports/{report_id}/review", json={"approved": True}, headers={"x-permission-scopes": "report:review"})
    assert reviewed.json()["status"] == "approved"

    headers = {"x-permission-scopes": "report:read,report:submit"}
    first = client.post(f"/reports/{report_id}/submit", headers=headers)
    second = client.post(f"/reports/{report_id}/submit", headers=headers)
    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json()["submission_id"] == second.json()["submission_id"]


def test_report_aggregates_email_and_approved_meeting_minutes() -> None:
    client = TestClient(app)
    minutes = {
        "title": "多数据源日报评审会",
        "meeting_date": "2026-07-28",
        "segments": [
            {
                "segment_id": "segment-multi-source",
                "text": "确认完成邮件和会议纪要聚合。",
                "confidence": 0.95,
            }
        ],
    }
    assert client.post("/meetings/meeting-multi-source/minutes", json=minutes).status_code == 200
    assert (
        client.post(
            "/meetings/meeting-multi-source/reviews",
            json={"approved": True},
            headers={"x-permission-scopes": "meeting:review"},
        ).status_code
        == 200
    )

    generated = client.post(
        "/reports/generate",
        json={"report_date": "2026-07-28"},
    )

    assert generated.status_code == 200
    evidence_ids = generated.json()["evidence_event_ids"]
    assert any(item.startswith("gitlab:") for item in evidence_ids)
    assert any(item.startswith("task:") for item in evidence_ids)
    assert any(item.startswith("email:") for item in evidence_ids)
    assert any(item.startswith("meeting:") for item in evidence_ids)
