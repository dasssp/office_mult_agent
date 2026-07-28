from app.agents.supervisor.graph import build_supervisor_graph
from app.schemas import Intent


def test_routes_daily_report() -> None:
    result = asyncio.run(build_supervisor_graph().ainvoke({"message": "请生成今天的日报", "task_input": {"report_date": "2026-07-28", "events": []}}))
    assert result["intent"] is Intent.DAILY_REPORT
    assert result["status"] == "routed"


def test_supervisor_invokes_email_subagent_tool() -> None:
    result = build_supervisor_graph().invoke({"message": "请润色这封邮件"})
    assert result["status"] == "completed"
    assert result["subagent_result"]["status"] == "draft"


def test_supervisor_invokes_data_analysis_subagent_tool() -> None:
    result = build_supervisor_graph().invoke(
        {"message": "分析 CSV 数据", "task_input": {"rows": [{"amount": 1}, {"amount": None}]}}
    )
    assert result["status"] == "completed"
    assert result["subagent_result"]["null_counts"] == {"amount": 1}


def test_supervisor_invokes_meeting_minutes_subagent_tool() -> None:
    result = asyncio.run(build_supervisor_graph().ainvoke({"message": "生成会议纪要", "task_input": {"meeting_id": "m1", "title": "周会", "segments": [{"segment_id": "s1", "text": "确认发布", "confidence": 0.9}]}}))
    assert result["subagent_result"]["status"] == "draft"


def test_supervisor_invokes_report_subagent_tool() -> None:
    result = asyncio.run(build_supervisor_graph().ainvoke({"message": "生成日报", "task_input": {"report_date": "2026-07-28", "events": [{"event_id": "e1", "title": "完成接口", "status": "completed"}]}}))
    assert result["subagent_result"]["completed"] == ["完成接口"]
import asyncio
