import json
from datetime import date, timedelta
from typing import Annotated, Literal, TypedDict

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, START, StateGraph, add_messages
from langgraph.runtime import Runtime
from langgraph.types import interrupt
from pydantic import BaseModel, Field

from app.orchestration.tools import DeepAgentDependencies
from app.schemas import RequestContext
from app.schemas.workflows import TranscriptSegment, WorkEvent
from app.services.work_events import MultiSourceWorkEventCollector


class ReportTaskSpec(BaseModel):
    operation: Literal["draft", "review", "submit"]
    report_date: str | None = None
    report_type: Literal["daily", "weekly"] = "daily"
    events: list[WorkEvent] = Field(default_factory=list)
    report_id: str | None = None
    approved: bool = True
    comment: str | None = None


class MeetingTaskSpec(BaseModel):
    operation: Literal["transcribe", "generate", "review", "send"]
    meeting_id: str
    title: str | None = None
    meeting_date: str | None = None
    segments: list[TranscriptSegment] = Field(default_factory=list)
    approved: bool = True
    comment: str | None = None


class DomainState(TypedDict, total=False):
    messages: Annotated[list[BaseMessage], add_messages]
    spec: ReportTaskSpec | MeetingTaskSpec
    result: dict[str, object]
    status: str
    warnings: list[str]


def _human_text(state: DomainState) -> str:
    for message in reversed(state.get("messages", [])):
        if isinstance(message, HumanMessage):
            return message.text
    return ""


def _decision_approved(value: object) -> bool:
    if not isinstance(value, dict):
        return False
    decisions = value.get("decisions")
    if not isinstance(decisions, list) or not decisions:
        return False
    decision = decisions[0]
    return isinstance(decision, dict) and decision.get("type") == "approve"


def _approval_request(
    tool_name: str, arguments: dict[str, object]
) -> dict[str, object]:
    return {
        "action_requests": [
            {
                "name": tool_name,
                "args": arguments,
                "description": f"受控操作 {tool_name} 正在等待人工审核",
            }
        ],
        "review_configs": [
            {
                "action_name": tool_name,
                "allowed_decisions": ["approve", "reject"],
            }
        ],
    }


def _finalize(state: DomainState) -> DomainState:
    payload = {
        "status": state.get("status", "completed"),
        "result": state.get("result", {}),
        "warnings": state.get("warnings", []),
    }
    return {
        "messages": [AIMessage(content=json.dumps(payload, ensure_ascii=False))],
    }


def build_report_subgraph(
    *,
    model: BaseChatModel,
    dependencies: DeepAgentDependencies,
    checkpointer: BaseCheckpointSaver | None = None,
):
    async def parse_task(state: DomainState) -> DomainState:
        structured = model.with_structured_output(ReportTaskSpec)
        spec = await structured.ainvoke(
            [
                SystemMessage(
                    content=(
                        "将任务解析为报告操作。只提取用户明确提供的字段；"
                        "缺失字段保持为空，不得猜测 report_id。"
                    )
                ),
                HumanMessage(content=_human_text(state)),
            ]
        )
        return {"spec": ReportTaskSpec.model_validate(spec), "status": "parsed"}

    async def prepare_draft(
        state: DomainState,
        runtime: Runtime[RequestContext],
    ) -> DomainState:
        spec = ReportTaskSpec.model_validate(state["spec"])
        if not spec.report_date:
            return {
                "status": "failed",
                "warnings": ["报告草稿缺少 report_date。"],
                "result": {},
            }
        events = spec.events
        source_warnings: list[str] = []
        if not events:
            date_to = spec.report_date
            if spec.report_type == "weekly":
                date_to = (
                    date.fromisoformat(spec.report_date) + timedelta(days=6)
                ).isoformat()
            collection = await MultiSourceWorkEventCollector(
                gitlab=dependencies.gitlab_connector,
                tasks=dependencies.task_connector,
                email=dependencies.email_connector,
                meeting_minutes=dependencies.meeting_agent,
            ).collect(
                date_from=spec.report_date,
                date_to=date_to,
                context=runtime.context,
            )
            events = collection.events
            source_warnings = collection.source_warnings
        if spec.report_type == "weekly":
            result = await dependencies.report_agent.generate_weekly(
                week_start=spec.report_date,
                events=events,
                source_warnings=source_warnings,
                context=runtime.context,
            )
        else:
            result = await dependencies.report_agent.generate_daily(
                report_date=spec.report_date,
                events=events,
                source_warnings=source_warnings,
                context=runtime.context,
            )
        return {"status": "completed", "result": result.model_dump(mode="json")}

    async def review(
        state: DomainState,
        runtime: Runtime[RequestContext],
    ) -> DomainState:
        spec = ReportTaskSpec.model_validate(state["spec"])
        if not spec.report_id:
            return {
                "status": "failed",
                "warnings": ["报告审核缺少 report_id。"],
                "result": {},
            }
        decision = interrupt(
            _approval_request(
                "review_report",
                {"report_id": spec.report_id, "approved": spec.approved},
            )
        )
        if not _decision_approved(decision):
            return {
                "status": "blocked",
                "warnings": ["用户拒绝执行报告审核。"],
                "result": {},
            }
        result = await dependencies.report_agent.review(
            report_id=spec.report_id,
            approved=spec.approved,
            comment=spec.comment,
            context=runtime.context,
            permissions=dependencies.permissions,
            audit=dependencies.audit,
        )
        return {"status": "completed", "result": result.model_dump(mode="json")}

    async def submit(
        state: DomainState,
        runtime: Runtime[RequestContext],
    ) -> DomainState:
        spec = ReportTaskSpec.model_validate(state["spec"])
        if not spec.report_id:
            return {
                "status": "failed",
                "warnings": ["报告提交缺少 report_id。"],
                "result": {},
            }
        decision = interrupt(
            _approval_request("submit_report", {"report_id": spec.report_id})
        )
        if not _decision_approved(decision):
            return {
                "status": "blocked",
                "warnings": ["用户拒绝提交报告。"],
                "result": {},
            }
        result = await dependencies.report_agent.submit(
            report_id=spec.report_id,
            context=runtime.context,
            connector=dependencies.report_connector,
            permissions=dependencies.permissions,
            audit=dependencies.audit,
        )
        return {"status": "completed", "result": result.model_dump(mode="json")}

    def route(state: DomainState) -> str:
        return ReportTaskSpec.model_validate(state["spec"]).operation

    graph = StateGraph(DomainState, context_schema=RequestContext)
    graph.add_node("parse_report_task", parse_task)
    graph.add_node("draft_report", prepare_draft)
    graph.add_node("review_report", review)
    graph.add_node("submit_report", submit)
    graph.add_node("finalize_report", _finalize)
    graph.add_edge(START, "parse_report_task")
    graph.add_conditional_edges(
        "parse_report_task",
        route,
        {
            "draft": "draft_report",
            "review": "review_report",
            "submit": "submit_report",
        },
    )
    for node in ("draft_report", "review_report", "submit_report"):
        graph.add_edge(node, "finalize_report")
    graph.add_edge("finalize_report", END)
    return graph.compile(checkpointer=checkpointer)


def build_meeting_subgraph(
    *,
    model: BaseChatModel,
    dependencies: DeepAgentDependencies,
    checkpointer: BaseCheckpointSaver | None = None,
):
    async def parse_task(state: DomainState) -> DomainState:
        structured = model.with_structured_output(MeetingTaskSpec)
        spec = await structured.ainvoke(
            [
                SystemMessage(
                    content=(
                        "将任务解析为会议纪要操作。只使用明确提供的 meeting_id、"
                        "title、meeting_date 和转写片段，不猜测负责人或截止日期。"
                    )
                ),
                HumanMessage(content=_human_text(state)),
            ]
        )
        return {"spec": MeetingTaskSpec.model_validate(spec), "status": "parsed"}

    async def transcribe(
        state: DomainState,
        runtime: Runtime[RequestContext],
    ) -> DomainState:
        spec = MeetingTaskSpec.model_validate(state["spec"])
        task = await dependencies.background_tasks.create(
            kind="meeting_transcription",
            payload={"meeting_id": spec.meeting_id},
            context=runtime.context,
        )
        return {
            "status": "queued",
            "result": {
                "background_task_id": task.task_id,
                "status": task.status,
            },
        }

    async def generate(
        state: DomainState,
        runtime: Runtime[RequestContext],
    ) -> DomainState:
        spec = MeetingTaskSpec.model_validate(state["spec"])
        title = spec.title
        meeting_date = spec.meeting_date
        if title is None or meeting_date is None:
            meeting = await dependencies.meeting_connector.get_meeting(
                meeting_id=spec.meeting_id,
                context=runtime.context,
            )
            if title is None:
                title = str(meeting.get("title", "会议纪要"))
            if meeting_date is None:
                raw_date = meeting.get("meeting_date") or meeting.get("start_time")
                if raw_date:
                    meeting_date = str(raw_date)[:10]
        result = await dependencies.meeting_agent.generate(
            meeting_id=spec.meeting_id,
            title=title,
            segments=spec.segments,
            context=runtime.context,
            meeting_date=meeting_date,
        )
        return {"status": "completed", "result": result.model_dump(mode="json")}

    async def review(
        state: DomainState,
        runtime: Runtime[RequestContext],
    ) -> DomainState:
        spec = MeetingTaskSpec.model_validate(state["spec"])
        decision = interrupt(
            _approval_request(
                "review_meeting_minutes",
                {"meeting_id": spec.meeting_id, "approved": spec.approved},
            )
        )
        if not _decision_approved(decision):
            return {
                "status": "blocked",
                "warnings": ["用户拒绝执行会议纪要审核。"],
                "result": {},
            }
        result = await dependencies.meeting_agent.review(
            meeting_id=spec.meeting_id,
            approved=spec.approved,
            comment=spec.comment,
            context=runtime.context,
            permissions=dependencies.permissions,
            audit=dependencies.audit,
        )
        return {"status": "completed", "result": result.model_dump(mode="json")}

    async def send(
        state: DomainState,
        runtime: Runtime[RequestContext],
    ) -> DomainState:
        spec = MeetingTaskSpec.model_validate(state["spec"])
        decision = interrupt(
            _approval_request(
                "send_meeting_minutes",
                {"meeting_id": spec.meeting_id},
            )
        )
        if not _decision_approved(decision):
            return {
                "status": "blocked",
                "warnings": ["用户拒绝发送会议纪要。"],
                "result": {},
            }
        result = await dependencies.meeting_agent.send(
            meeting_id=spec.meeting_id,
            context=runtime.context,
            connector=dependencies.email_connector,
            permissions=dependencies.permissions,
            audit=dependencies.audit,
        )
        return {"status": "completed", "result": result.model_dump(mode="json")}

    def route(state: DomainState) -> str:
        return MeetingTaskSpec.model_validate(state["spec"]).operation

    graph = StateGraph(DomainState, context_schema=RequestContext)
    graph.add_node("parse_meeting_task", parse_task)
    graph.add_node("enqueue_transcription", transcribe)
    graph.add_node("generate_minutes", generate)
    graph.add_node("review_minutes", review)
    graph.add_node("send_minutes", send)
    graph.add_node("finalize_meeting", _finalize)
    graph.add_edge(START, "parse_meeting_task")
    graph.add_conditional_edges(
        "parse_meeting_task",
        route,
        {
            "transcribe": "enqueue_transcription",
            "generate": "generate_minutes",
            "review": "review_minutes",
            "send": "send_minutes",
        },
    )
    for node in (
        "enqueue_transcription",
        "generate_minutes",
        "review_minutes",
        "send_minutes",
    ):
        graph.add_edge(node, "finalize_meeting")
    graph.add_edge("finalize_meeting", END)
    return graph.compile(checkpointer=checkpointer)
