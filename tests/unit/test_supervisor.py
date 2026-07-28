from app.agents.supervisor.graph import build_supervisor_graph
from app.schemas import Intent


def test_routes_daily_report() -> None:
    result = build_supervisor_graph().invoke({"message": "请生成今天的日报"})
    assert result["intent"] is Intent.DAILY_REPORT
    assert result["status"] == "routed"


def test_supervisor_invokes_email_subagent_tool() -> None:
    result = build_supervisor_graph().invoke({"message": "请润色这封邮件"})
    assert result["status"] == "completed"
    assert result["subagent_result"]["status"] == "draft"
