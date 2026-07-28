from langgraph.graph import END, START, StateGraph

from app.agents.supervisor.state import SupervisorState
from app.schemas import Intent
from app.tools import build_subagent_tools


def _classify(message: str) -> Intent:
    text = message.lower()
    if ("分析" in text or "analysis" in text) and ("日报" in text or "report" in text):
        return Intent.COMPOSITE_TASK
    if "日报" in text or "daily report" in text:
        return Intent.DAILY_REPORT
    if "周报" in text or "weekly report" in text:
        return Intent.WEEKLY_REPORT
    if "会议纪要" in text or "meeting minutes" in text:
        return Intent.MEETING_MINUTES
    if "润色" in text or "polish" in text:
        return Intent.EMAIL_POLISH
    if "excel" in text or "csv" in text or "分析文件" in text:
        return Intent.FILE_ANALYSIS
    if "知识库" in text or "knowledge" in text:
        return Intent.KNOWLEDGE_QA
    return Intent.GENERAL_CHAT


def parse_request(state: SupervisorState) -> SupervisorState:
    return {"intent": _classify(state["message"]), "status": "routed"}


def prepare_result(state: SupervisorState) -> SupervisorState:
    intent = state["intent"]
    return {
        "result_message": f"任务已路由至 {intent.value}；仅 Supervisor 受控工具可调用专业 Agent。",
        "warnings": ["当前调用不执行外部系统写操作。"],
    }


def call_email_polish_agent(state: SupervisorState) -> SupervisorState:
    tool = next(item for item in build_subagent_tools() if item.name == "email_polish_tool")
    result = tool.invoke({"subject": "邮件润色草稿", "body": state["message"]})
    return {"subagent_result": result, "status": "completed"}


def call_data_analysis_agent(state: SupervisorState) -> SupervisorState:
    rows = state.get("task_input", {}).get("rows", [])
    if not isinstance(rows, list) or not all(isinstance(row, dict) for row in rows):
        return {"status": "failed", "warnings": ["数据分析需要 task_input.rows 数组。"]}
    tool = next(item for item in build_subagent_tools() if item.name == "data_analysis_tool")
    result = tool.invoke({"rows": rows})
    return {"subagent_result": result, "status": "completed"}


async def call_meeting_minutes_agent(state: SupervisorState) -> SupervisorState:
    payload = state.get("task_input", {})
    meeting_id, title, segments = payload.get("meeting_id"), payload.get("title"), payload.get("segments")
    if not isinstance(meeting_id, str) or not isinstance(title, str) or not isinstance(segments, list):
        return {"status": "failed", "warnings": ["会议纪要需要 meeting_id、title 和 segments。"]}
    tool = next(item for item in build_subagent_tools() if item.name == "meeting_minutes_tool")
    result = await tool.ainvoke({"meeting_id": meeting_id, "title": title, "segments": segments})
    return {"subagent_result": result, "status": "completed"}


async def call_report_agent(state: SupervisorState) -> SupervisorState:
    payload = state.get("task_input", {})
    report_date, events = payload.get("report_date"), payload.get("events")
    if not isinstance(report_date, str) or not isinstance(events, list):
        return {"status": "failed", "warnings": ["日报需要 report_date 和 events。"]}
    tool = next(item for item in build_subagent_tools() if item.name == "report_draft_tool")
    result = await tool.ainvoke({"report_date": report_date, "events": events})
    return {"subagent_result": result, "status": "completed"}


async def analyze_then_generate_report(state: SupervisorState) -> SupervisorState:
    payload = state.get("task_input", {})
    rows, report_date = payload.get("rows"), payload.get("report_date")
    if not isinstance(rows, list) or not isinstance(report_date, str):
        return {"status": "failed", "warnings": ["复合任务需要 rows 和 report_date。"]}
    tools = {item.name: item for item in build_subagent_tools()}
    analysis = tools["data_analysis_tool"].invoke({"rows": rows})
    event = {"event_id": "analysis:input", "title": f"完成数据分析：{analysis['row_count']} 行", "status": "completed", "evidence_url": "artifact://analysis/input"}
    report = await tools["report_draft_tool"].ainvoke({"report_date": report_date, "events": [event]})
    return {"subagent_result": {"analysis": analysis, "report": report}, "status": "completed"}


def route_after_parse(state: SupervisorState) -> str:
    if state["intent"] is Intent.EMAIL_POLISH:
        return "call_email_polish_agent"
    if state["intent"] is Intent.FILE_ANALYSIS:
        return "call_data_analysis_agent"
    if state["intent"] is Intent.MEETING_MINUTES:
        return "call_meeting_minutes_agent"
    if state["intent"] in {Intent.DAILY_REPORT, Intent.WEEKLY_REPORT}:
        return "call_report_agent"
    if state["intent"] is Intent.COMPOSITE_TASK:
        return "analyze_then_generate_report"
    return "prepare_result"


def build_supervisor_graph():
    # Registered tools are intentionally narrow; state graph keeps orchestration deterministic.
    build_subagent_tools()
    graph = StateGraph(SupervisorState)
    graph.add_node("parse_request", parse_request)
    graph.add_node("prepare_result", prepare_result)
    graph.add_node("call_email_polish_agent", call_email_polish_agent)
    graph.add_node("call_data_analysis_agent", call_data_analysis_agent)
    graph.add_node("call_meeting_minutes_agent", call_meeting_minutes_agent)
    graph.add_node("call_report_agent", call_report_agent)
    graph.add_node("analyze_then_generate_report", analyze_then_generate_report)
    graph.add_edge(START, "parse_request")
    graph.add_conditional_edges("parse_request", route_after_parse)
    graph.add_edge("call_email_polish_agent", "prepare_result")
    graph.add_edge("call_data_analysis_agent", "prepare_result")
    graph.add_edge("call_meeting_minutes_agent", "prepare_result")
    graph.add_edge("call_report_agent", "prepare_result")
    graph.add_edge("analyze_then_generate_report", "prepare_result")
    graph.add_edge("prepare_result", END)
    return graph.compile()
