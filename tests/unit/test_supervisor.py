from app.agents.supervisor.graph import build_supervisor_graph
from app.schemas import Intent


def test_routes_daily_report() -> None:
    result = build_supervisor_graph().invoke({"message": "请生成今天的日报"})
    assert result["intent"] is Intent.DAILY_REPORT
    assert result["status"] == "routed"
