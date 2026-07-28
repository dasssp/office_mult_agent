from fastapi.testclient import TestClient

from app.main import app


def test_meeting_requires_review_before_idempotent_send() -> None:
    client = TestClient(app)
    payload = {"title": "项目周会", "segments": [{"segment_id": "s1", "text": "确认下周发布", "confidence": 0.9}]}
    assert client.post("/meetings/m1/minutes", json=payload).status_code == 200
    assert client.post("/meetings/m1/send").status_code == 403
    assert client.post("/meetings/m1/reviews", json={"approved": True}).status_code == 403
    assert client.post("/meetings/m1/reviews", json={"approved": True}, headers={"x-permission-scopes": "meeting:review"}).status_code == 200
    headers = {"x-permission-scopes": "report:read,meeting:send"}
    first = client.post("/meetings/m1/send", headers=headers)
    second = client.post("/meetings/m1/send", headers=headers)
    assert first.status_code == 200
    assert first.json()["message_id"] == second.json()["message_id"]


def test_meeting_minutes_are_isolated_by_tenant() -> None:
    client = TestClient(app)
    payload = {
        "title": "私密会议",
        "segments": [{"segment_id": "s1", "text": "内部事项", "confidence": 0.9}],
    }
    assert (
        client.post(
            "/meetings/shared-id/minutes",
            json=payload,
            headers={"x-tenant-id": "tenant-a"},
        ).status_code
        == 200
    )
    response = client.post(
        "/meetings/shared-id/reviews",
        json={"approved": True},
        headers={
            "x-tenant-id": "tenant-b",
            "x-permission-scopes": "meeting:review",
        },
    )
    assert response.status_code == 404
