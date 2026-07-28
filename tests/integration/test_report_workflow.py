from fastapi.testclient import TestClient

from app.main import app


def test_report_requires_approval_then_submits_idempotently() -> None:
    client = TestClient(app)
    generated = client.post("/reports/generate", json={"report_date": "2026-07-28", "use_mock_sources": True})
    assert generated.status_code == 200
    report_id = generated.json()["report_id"]

    assert client.post(f"/reports/{report_id}/submit").status_code == 403
    reviewed = client.post(f"/reports/{report_id}/review", json={"approved": True})
    assert reviewed.json()["status"] == "approved"

    headers = {"x-permission-scopes": "report:read,report:submit"}
    first = client.post(f"/reports/{report_id}/submit", headers=headers)
    second = client.post(f"/reports/{report_id}/submit", headers=headers)
    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json()["submission_id"] == second.json()["submission_id"]
