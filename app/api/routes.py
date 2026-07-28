from datetime import date, timedelta

from fastapi import APIRouter, File, HTTPException, Request, UploadFile
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Command

from app.agents.data_analysis_agent import DataAnalysisAgent
from app.agents.email_polish_agent import EmailPolishAgent
from app.agents.knowledge_agent import KnowledgeAgent
from app.agents.meeting_minutes_agent import MeetingMinutesAgent
from app.agents.report_agent import ReportAgent
from app.agents.supervisor import build_supervisor_graph
from app.config import get_settings
from app.connectors.mocks.email import MockEmailConnector
from app.connectors.mocks.report_system import MockReportSystemConnector
from app.connectors.registry import ConnectorRegistry, ConnectorUnavailableError
from app.middleware.context import build_development_context
from app.schemas import (
    AssistantInvokeRequest,
    AssistantInvokeResponse,
    AssistantResumeRequest,
    AssistantStateResponse,
)
from app.schemas.workflows import (
    BackgroundTaskResponse,
    DataAnalysisRequest,
    DataAnalysisResult,
    EmailPolishDraft,
    EmailPolishRequest,
    KnowledgeAnswer,
    KnowledgeQueryRequest,
    MeetingEmailStatus,
    MeetingMinutesDraft,
    MeetingMinutesRequest,
    MeetingReviewRequest,
    ReportDraft,
    ReportGenerateRequest,
    ReportReviewRequest,
    ReportSubmission,
)
from app.services.approvals import ApprovalService
from app.services.artifacts import ArtifactService
from app.services.audit import AuditService
from app.services.files import FileService, UnsafeFileError
from app.services.permissions import PermissionService
from app.services.runtime_state import BackgroundTask, BackgroundTaskService
from app.services.work_events import MultiSourceWorkEventCollector

router = APIRouter()
_graph = build_supervisor_graph(checkpointer=InMemorySaver())
_approvals = ApprovalService()
_report_agent = ReportAgent()
_report_connector = MockReportSystemConnector()
_permissions = PermissionService()
_audit = AuditService()
_meeting_agent = MeetingMinutesAgent()
_email_connector = MockEmailConnector()
_files = FileService()
_artifacts = ArtifactService()
_connectors = ConnectorRegistry.for_environment("development")
_background_tasks = BackgroundTaskService()


def _report_agent_for(request: Request) -> ReportAgent:
    return getattr(request.app.state, "report_agent", _report_agent)


def _audit_for(request: Request) -> AuditService:
    return getattr(request.app.state, "audit", _audit)


def _graph_for(request: Request):
    return getattr(request.app.state, "graph", _graph)


def _approvals_for(request: Request) -> ApprovalService:
    return getattr(request.app.state, "approvals", _approvals)


def _knowledge_agent_for(request: Request) -> KnowledgeAgent:
    return getattr(request.app.state, "knowledge_agent", KnowledgeAgent())


def _meeting_agent_for(request: Request) -> MeetingMinutesAgent:
    return getattr(request.app.state, "meeting_agent", _meeting_agent)


def _connectors_for(request: Request) -> ConnectorRegistry:
    return getattr(request.app.state, "connectors", _connectors)


def _files_for(request: Request) -> FileService:
    return getattr(request.app.state, "files", _files)


def _artifacts_for(request: Request) -> ArtifactService:
    return getattr(request.app.state, "artifacts", _artifacts)


def _background_tasks_for(request: Request) -> BackgroundTaskService:
    return getattr(request.app.state, "background_tasks", _background_tasks)


def _task_response(task: BackgroundTask) -> BackgroundTaskResponse:
    return BackgroundTaskResponse(
        task_id=task.task_id,
        kind=task.kind,
        status=task.status,
        progress=task.progress,
        attempts=task.attempts,
        max_attempts=task.max_attempts,
        cancel_requested=task.cancel_requested,
        result=task.result,
        error_code=task.error_code,
    )


@router.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/ready")
async def readiness(request: Request) -> dict[str, str]:
    if get_settings().app_env == "production" and not hasattr(request.app.state, "database"):
        raise HTTPException(status_code=503, detail="database is not initialized")
    return {"status": "ready"}


@router.post("/assistant/invoke", response_model=AssistantInvokeResponse)
async def invoke_assistant(
    payload: AssistantInvokeRequest, request: Request
) -> AssistantInvokeResponse:
    context = build_development_context(request, payload.thread_id)
    task_input = {**payload.task_input, "require_approval": payload.require_approval}
    config = {"configurable": {"thread_id": payload.thread_id}}
    graph = _graph_for(request)
    result = await graph.ainvoke(
        {"message": payload.message, "task_input": task_input}, config, context=context
    )
    if "__interrupt__" in result:
        await _approvals_for(request).request(
            target_type="assistant_thread", target_id=payload.thread_id, context=context
        )
        state = await graph.aget_state(config)
        return AssistantInvokeResponse(
            request_id=context.request_id,
            thread_id=context.thread_id,
            intent=state.values["intent"],
            status="awaiting_approval",
            message="draft is awaiting human approval",
            warnings=[],
            awaiting_approval=True,
            result=state.values.get("subagent_result"),
        )
    return AssistantInvokeResponse(
        request_id=context.request_id,
        thread_id=context.thread_id,
        intent=result["intent"],
        status=result["status"],
        message=result["result_message"],
        warnings=result["warnings"],
        result=result.get("result") or result.get("subagent_result"),
    )


@router.post("/knowledge/answer", response_model=KnowledgeAnswer)
async def answer_knowledge(payload: KnowledgeQueryRequest, request: Request) -> KnowledgeAnswer:
    context = build_development_context(request, thread_id="knowledge:query")
    try:
        return await _knowledge_agent_for(request).answer(
            query=payload.query, context=context, permissions=_permissions
        )
    except PermissionError as error:
        raise HTTPException(status_code=403, detail=str(error)) from error
    except (RuntimeError, ValueError) as error:
        raise HTTPException(status_code=503, detail="knowledge service unavailable") from error


async def _require_pending_approval(thread_id: str, request: Request):
    context = build_development_context(request, thread_id)
    try:
        await _approvals_for(request).require_pending(
            target_type="assistant_thread", target_id=thread_id, context=context
        )
    except KeyError:
        raise HTTPException(status_code=404, detail="pending approval not found")
    snapshot = await _graph_for(request).aget_state(
        {"configurable": {"thread_id": thread_id}}
    )
    required_scope = str(snapshot.values.get("required_scope", "report:review"))
    try:
        _permissions.require(context, required_scope)
    except PermissionError as error:
        raise HTTPException(status_code=403, detail=str(error)) from error
    return context


@router.post("/assistant/{thread_id}/resume", response_model=AssistantInvokeResponse)
async def resume_assistant(
    thread_id: str, payload: AssistantResumeRequest, request: Request
) -> AssistantInvokeResponse:
    context = await _require_pending_approval(thread_id, request)
    result = await _graph_for(request).ainvoke(
        Command(resume=payload.model_dump()),
        {"configurable": {"thread_id": thread_id}},
        context=context,
    )
    await _approvals_for(request).decide(
        target_type="assistant_thread",
        target_id=thread_id,
        approved=payload.approved,
        comment=payload.comment,
        context=context,
    )
    awaiting_approval = "__interrupt__" in result
    if awaiting_approval:
        await _approvals_for(request).request(
            target_type="assistant_thread",
            target_id=thread_id,
            context=context,
        )
    return AssistantInvokeResponse(
        request_id=context.request_id,
        thread_id=thread_id,
        intent=result["intent"],
        status=result["status"],
        message=result["result_message"],
        warnings=result["warnings"],
        awaiting_approval=awaiting_approval,
        result=result.get("result") or result.get("subagent_result"),
    )


@router.get("/assistant/{thread_id}/state", response_model=AssistantStateResponse)
async def assistant_state(thread_id: str, request: Request) -> AssistantStateResponse:
    await _require_pending_approval(thread_id, request)
    snapshot = await _graph_for(request).aget_state({"configurable": {"thread_id": thread_id}})
    return AssistantStateResponse(
        thread_id=thread_id,
        status=str(snapshot.values.get("status", "unknown")),
        awaiting_approval=bool(snapshot.next),
        next_nodes=list(snapshot.next),
        pending_actions=[
            str(item) for item in snapshot.values.get("pending_actions", [])
        ],
        required_scope=(
            str(snapshot.values["required_scope"])
            if snapshot.values.get("required_scope")
            else None
        ),
    )


@router.post("/reports/generate", response_model=ReportDraft)
async def generate_report(payload: ReportGenerateRequest, request: Request) -> ReportDraft:
    context = build_development_context(request, thread_id=f"report:new:{payload.report_date}")
    agent = _report_agent_for(request)
    source_warnings: list[str] = []
    if payload.events:
        events = payload.events
    elif payload.use_mock_sources:
        events = await agent.collect_mock_events()
    else:
        date_to = payload.report_date
        if payload.report_type == "weekly":
            date_to = (
                date.fromisoformat(payload.report_date) + timedelta(days=6)
            ).isoformat()
        connectors = _connectors_for(request)
        collection = await MultiSourceWorkEventCollector(
            gitlab=connectors.gitlab,
            tasks=connectors.task,
            email=connectors.email,
            meeting_minutes=_meeting_agent_for(request),
        ).collect(
            date_from=payload.report_date,
            date_to=date_to,
            context=context,
        )
        events = collection.events
        source_warnings = collection.source_warnings
    if payload.report_type == "weekly":
        return await agent.generate_weekly(
            week_start=payload.report_date,
            events=events,
            source_warnings=source_warnings,
            context=context,
        )
    return await agent.generate_daily(
        report_date=payload.report_date,
        events=events,
        source_warnings=source_warnings,
        context=context,
    )


@router.post("/reports/{report_id}/review", response_model=ReportDraft)
async def review_report(
    report_id: str, payload: ReportReviewRequest, request: Request
) -> ReportDraft:
    context = build_development_context(request, thread_id=f"report:{report_id}")
    try:
        return await _report_agent_for(request).review(
            report_id=report_id,
            approved=payload.approved,
            comment=payload.comment,
            context=context,
            permissions=_permissions,
            audit=_audit_for(request),
        )
    except KeyError as error:
        raise HTTPException(status_code=404, detail="report not found") from error
    except PermissionError as error:
        raise HTTPException(status_code=403, detail=str(error)) from error


@router.post("/reports/{report_id}/submit", response_model=ReportSubmission)
async def submit_report(report_id: str, request: Request) -> ReportSubmission:
    context = build_development_context(request, thread_id=f"report:{report_id}")
    try:
        return await _report_agent_for(request).submit(
            report_id=report_id,
            context=context,
            connector=_connectors_for(request).report_system,
            permissions=_permissions,
            audit=_audit_for(request),
        )
    except KeyError as error:
        raise HTTPException(status_code=404, detail="report not found") from error
    except PermissionError as error:
        raise HTTPException(status_code=403, detail=str(error)) from error
    except ValueError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    except ConnectorUnavailableError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error


@router.post("/meetings/{meeting_id}/minutes", response_model=MeetingMinutesDraft)
async def generate_minutes(
    meeting_id: str, payload: MeetingMinutesRequest, request: Request
) -> MeetingMinutesDraft:
    context = build_development_context(request, thread_id=f"meeting:{meeting_id}")
    return await _meeting_agent_for(request).generate(
        meeting_id=meeting_id,
        title=payload.title,
        segments=payload.segments,
        context=context,
        meeting_date=payload.meeting_date,
    )


@router.post(
    "/meetings/{meeting_id}/transcriptions",
    response_model=BackgroundTaskResponse,
    status_code=202,
)
async def start_meeting_transcription(
    meeting_id: str, request: Request
) -> BackgroundTaskResponse:
    context = build_development_context(
        request, thread_id=f"meeting:{meeting_id}:transcription"
    )
    try:
        _permissions.require(context, "meeting:transcribe")
        task = await _background_tasks_for(request).create(
            kind="meeting_transcription",
            payload={"meeting_id": meeting_id},
            context=context,
        )
        return _task_response(task)
    except PermissionError as error:
        raise HTTPException(status_code=403, detail=str(error)) from error


@router.get("/tasks/{task_id}", response_model=BackgroundTaskResponse)
async def get_background_task(
    task_id: str, request: Request
) -> BackgroundTaskResponse:
    context = build_development_context(request, thread_id=f"task:{task_id}")
    try:
        task = await _background_tasks_for(request).get(task_id, context)
        return _task_response(task)
    except KeyError as error:
        raise HTTPException(status_code=404, detail="task not found") from error


@router.post("/tasks/{task_id}/cancel", response_model=BackgroundTaskResponse)
async def cancel_background_task(
    task_id: str, request: Request
) -> BackgroundTaskResponse:
    context = build_development_context(request, thread_id=f"task:{task_id}")
    try:
        _permissions.require(context, "task:cancel")
        task = await _background_tasks_for(request).cancel(task_id, context)
        return _task_response(task)
    except KeyError as error:
        raise HTTPException(status_code=404, detail="task not found") from error
    except PermissionError as error:
        raise HTTPException(status_code=403, detail=str(error)) from error


@router.post("/meetings/{meeting_id}/reviews", response_model=MeetingMinutesDraft)
async def review_minutes(
    meeting_id: str, payload: MeetingReviewRequest, request: Request
) -> MeetingMinutesDraft:
    context = build_development_context(request, thread_id=f"meeting:{meeting_id}")
    try:
        return await _meeting_agent_for(request).review(
            meeting_id=meeting_id,
            approved=payload.approved,
            comment=payload.comment,
            context=context,
            permissions=_permissions,
            audit=_audit,
        )
    except KeyError as error:
        raise HTTPException(status_code=404, detail="meeting minutes not found") from error
    except PermissionError as error:
        raise HTTPException(status_code=403, detail=str(error)) from error


@router.post("/meetings/{meeting_id}/send", response_model=MeetingEmailStatus)
async def send_minutes(meeting_id: str, request: Request) -> MeetingEmailStatus:
    context = build_development_context(request, thread_id=f"meeting:{meeting_id}")
    try:
        return await _meeting_agent_for(request).send(
            meeting_id=meeting_id,
            context=context,
            connector=_connectors_for(request).email,
            permissions=_permissions,
            audit=_audit,
        )
    except KeyError as error:
        raise HTTPException(status_code=404, detail="meeting minutes not found") from error
    except PermissionError as error:
        raise HTTPException(status_code=403, detail=str(error)) from error
    except ValueError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    except ConnectorUnavailableError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error


@router.post("/emails/polish", response_model=EmailPolishDraft)
async def polish_email(payload: EmailPolishRequest) -> EmailPolishDraft:
    return EmailPolishAgent().polish(
        subject=payload.subject, body=payload.body, attachments=payload.attachments
    )


@router.post("/analysis/run", response_model=DataAnalysisResult)
async def analyze_data(payload: DataAnalysisRequest) -> DataAnalysisResult:
    return DataAnalysisAgent().analyze(rows=payload.rows)


@router.post("/analysis/files/{file_id}", response_model=DataAnalysisResult)
async def analyze_uploaded_file(file_id: str, request: Request) -> DataAnalysisResult:
    context = build_development_context(request, thread_id=f"file:{file_id}")
    try:
        return DataAnalysisAgent().analyze(
            rows=await _files_for(request).get_rows(file_id, context)
        )
    except KeyError as error:
        raise HTTPException(status_code=404, detail="file not found") from error


@router.post("/analysis/files/{file_id}/export")
async def export_uploaded_analysis(file_id: str, request: Request) -> dict[str, str]:
    context = build_development_context(request, thread_id=f"file:{file_id}")
    try:
        result = DataAnalysisAgent().analyze(
            rows=await _files_for(request).get_rows(file_id, context)
        )
        result.source_file_id = file_id
        return await _artifacts_for(request).export_analysis(result, context)
    except KeyError as error:
        raise HTTPException(status_code=404, detail="file not found") from error


@router.get("/files/{file_id}/metadata")
async def file_metadata(file_id: str, request: Request) -> dict[str, object]:
    context = build_development_context(request, thread_id=f"file:{file_id}")
    try:
        return (await _files_for(request).get_metadata(file_id, context)).as_dict()
    except KeyError as error:
        raise HTTPException(status_code=404, detail="file not found") from error


@router.post("/files/upload")
async def upload_file(request: Request, file: UploadFile = File(...)) -> dict[str, str]:
    context = build_development_context(request, thread_id="file:upload")
    try:
        file_id = await _files_for(request).store_and_parse(
            filename=file.filename or "",
            content=await file.read(),
            content_type=file.content_type,
            context=context,
        )
        return {"file_id": file_id, "status": "stored"}
    except (UnicodeDecodeError, UnsafeFileError) as error:
        raise HTTPException(status_code=422, detail=str(error)) from error


@router.delete("/files/{file_id}")
async def delete_file(file_id: str, request: Request) -> dict[str, str]:
    context = build_development_context(request, thread_id=f"file:{file_id}")
    try:
        _permissions.require(context, "file:delete")
        await _files_for(request).delete(file_id, context)
        await _audit_for(request).record(action="file.delete", context=context, target_id=file_id)
        return {"file_id": file_id, "status": "deleted"}
    except KeyError as error:
        raise HTTPException(status_code=404, detail="file not found") from error
    except PermissionError as error:
        raise HTTPException(status_code=403, detail=str(error)) from error
