from langgraph.graph import END, START, StateGraph

from app.agents.supervisor.state import SupervisorState
from app.schemas import Intent
from app.tools import build_subagent_tools


def _classify(message: str) -> Intent:
    text = message.lower()
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


def route_after_parse(state: SupervisorState) -> str:
    return "call_email_polish_agent" if state["intent"] is Intent.EMAIL_POLISH else "prepare_result"


def build_supervisor_graph():
    # Registered tools are intentionally narrow; state graph keeps orchestration deterministic.
    build_subagent_tools()
    graph = StateGraph(SupervisorState)
    graph.add_node("parse_request", parse_request)
    graph.add_node("prepare_result", prepare_result)
    graph.add_node("call_email_polish_agent", call_email_polish_agent)
    graph.add_edge(START, "parse_request")
    graph.add_conditional_edges("parse_request", route_after_parse)
    graph.add_edge("call_email_polish_agent", "prepare_result")
    graph.add_edge("prepare_result", END)
    return graph.compile()
