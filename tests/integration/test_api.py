from fastapi.testclient import TestClient

from app.main import app


def test_health_and_assistant_invoke() -> None:
    client = TestClient(app)
    assert client.get("/health").json() == {"status": "ok"}
    response = client.post("/assistant/invoke", json={"thread_id": "thread-1", "message": "帮我生成日报"})
    assert response.status_code == 200
    assert response.json()["intent"] == "daily_report"
