from app.agents.supervisor.graph import build_supervisor_graph
from app.schemas import Intent, RequestContext


def _context() -> RequestContext:
    return RequestContext(
        thread_id="supervisor-test",
        tenant_id="tenant-a",
        operator_id="operator-a",
    )


def test_routes_daily_report() -> None:
    result = asyncio.run(build_supervisor_graph().ainvoke({"message": "请生成今天的日报", "task_input": {"report_date": "2026-07-28", "events": []}}))
    assert result["intent"] is Intent.DAILY_REPORT
    assert result["status"] == "completed"


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
    result = asyncio.run(build_supervisor_graph().ainvoke({"message": "生成会议纪要", "task_input": {"meeting_id": "m1", "title": "周会", "segments": [{"segment_id": "s1", "text": "确认发布", "confidence": 0.9}]}}, context=_context()))
    assert result["subagent_result"]["status"] == "draft"


def test_supervisor_invokes_report_subagent_tool() -> None:
    result = asyncio.run(build_supervisor_graph().ainvoke({"message": "生成日报", "task_input": {"report_date": "2026-07-28", "events": [{"event_id": "e1", "title": "完成接口", "status": "completed"}]}}))
    assert result["subagent_result"]["completed"] == ["完成接口"]


def test_supervisor_runs_analysis_then_report() -> None:
    result = asyncio.run(build_supervisor_graph().ainvoke({"message": "分析数据并生成日报", "task_input": {"rows": [{"value": 1}], "report_date": "2026-07-28"}}))
    assert result["subagent_result"]["report"]["evidence_event_ids"] == ["analysis:input"]


def test_routes_all_controlled_p1_intents() -> None:
    graph = build_supervisor_graph()
    cases = {
        "请提交日报": Intent.REPORT_SUBMISSION,
        "审核会议结果": Intent.MEETING_REVIEW,
        "生成图表": Intent.CHART_GENERATION,
        "导出报告": Intent.REPORT_EXPORT,
        "记住我的报告偏好": Intent.MEMORY_MANAGEMENT,
    }
    for message, expected in cases.items():
        result = graph.invoke({"message": message})
        assert result["intent"] is expected
        assert result["plan"]
import asyncio
