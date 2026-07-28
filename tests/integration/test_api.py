from fastapi.testclient import TestClient

from app.main import app


def test_health_and_assistant_invoke() -> None:
    client = TestClient(app)
    assert client.get("/health").json() == {"status": "ok"}
    readiness = client.get("/ready")
    assert readiness.json() == {"status": "ready"}
    assert readiness.headers["x-content-type-options"] == "nosniff"
    assert readiness.headers["x-request-id"]
    response = client.post(
        "/assistant/invoke",
        json={
            "thread_id": "thread-1",
            "message": "帮我生成日报",
            "task_input": {"report_date": "2026-07-28", "events": []},
        },
    )
    assert response.status_code == 200
    assert response.json()["intent"] == "daily_report"
    assert response.json()["result"]["status"] == "draft"


def test_knowledge_query_requires_permission_and_returns_citations() -> None:
    client = TestClient(app)
    forbidden = client.post("/knowledge/answer", json={"query": "leave policy"})
    assert forbidden.status_code == 403
    allowed = client.post(
        "/knowledge/answer",
        json={"query": "leave policy"},
        headers={"x-permission-scopes": "knowledge:read"},
    )
    assert allowed.json()["citations"][0]["document_id"] == "mock-policy-1"


def test_supervisor_routes_knowledge_with_trusted_context() -> None:
    client = TestClient(app)
    response = client.post(
        "/assistant/invoke",
        json={"thread_id": "knowledge-thread", "message": "knowledge leave policy"},
        headers={"x-permission-scopes": "knowledge:read"},
    )
    assert response.status_code == 200
    assert response.json()["intent"] == "knowledge_qa"
    assert response.json()["status"] == "completed"


def test_runtime_rejects_oversized_request_before_parsing() -> None:
    client = TestClient(app)
    response = client.post("/assistant/invoke", content=b"x", headers={"content-length": "9999999"})
    assert response.status_code == 413
