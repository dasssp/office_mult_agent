from fastapi import APIRouter, File, HTTPException, Request, UploadFile
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Command

from app.agents.data_analysis_agent import DataAnalysisAgent
from app.agents.email_polish_agent import EmailPolishAgent
from app.agents.knowledge_agent import KnowledgeAgent
from app.agents.meeting_minutes_agent import MeetingMinutesAgent
from app.agents.report_agent import ReportAgent
from app.agents.supervisor import build_supervisor_graph
from app.connectors.mocks.email import MockEmailConnector
from app.connectors.mocks.report_system import MockReportSystemConnector
from app.middleware.context import build_development_context
from app.schemas import (
    AssistantInvokeRequest,
    AssistantInvokeResponse,
    AssistantResumeRequest,
    AssistantStateResponse,
)
from app.schemas.workflows import (
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
from app.services.artifacts import ArtifactService
from app.services.audit import AuditService
from app.services.files import FileService, UnsafeFileError
from app.services.permissions import PermissionService

router = APIRouter()
_graph = build_supervisor_graph(checkpointer=InMemorySaver())
_pending_approval_tenants: dict[str, str] = {}
_report_agent = ReportAgent()
_report_connector = MockReportSystemConnector()
_permissions = PermissionService()
_audit = AuditService()
_meeting_agent = MeetingMinutesAgent()
_email_connector = MockEmailConnector()
_files = FileService()
_artifacts = ArtifactService()


def _report_agent_for(request: Request) -> ReportAgent:
    return getattr(request.app.state, "report_agent", _report_agent)


def _audit_for(request: Request) -> AuditService:
    return getattr(request.app.state, "audit", _audit)


@router.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@router.post("/assistant/invoke", response_model=AssistantInvokeResponse)
async def invoke_assistant(payload: AssistantInvokeRequest, request: Request) -> AssistantInvokeResponse:
    context = build_development_context(request, payload.thread_id)
    task_input = {**payload.task_input, "require_approval": payload.require_approval}
    config = {"configurable": {"thread_id": payload.thread_id}}
    result = await _graph.ainvoke(
        {"message": payload.message, "task_input": task_input, "context": context}, config
    )
    if "__interrupt__" in result:
        _pending_approval_tenants[payload.thread_id] = context.tenant_id
        state = await _graph.aget_state(config)
        return AssistantInvokeResponse(
            request_id=context.request_id,
            thread_id=context.thread_id,
            intent=state.values["intent"],
            status="awaiting_approval",
            message="draft is awaiting human approval",
            warnings=[],
            awaiting_approval=True,
        )
    return AssistantInvokeResponse(
        request_id=context.request_id,
        thread_id=context.thread_id,
        intent=result["intent"],
        status=result["status"],
        message=result["result_message"],
        warnings=result["warnings"],
    )


@router.post("/knowledge/answer", response_model=KnowledgeAnswer)
async def answer_knowledge(payload: KnowledgeQueryRequest, request: Request) -> KnowledgeAnswer:
    context = build_development_context(request, thread_id="knowledge:query")
    try:
        return await KnowledgeAgent().answer(
            query=payload.query, context=context, permissions=_permissions
        )
    except PermissionError as error:
        raise HTTPException(status_code=403, detail=str(error)) from error


def _require_pending_approval(thread_id: str, request: Request) -> None:
    context = build_development_context(request, thread_id)
    tenant_id = _pending_approval_tenants.get(thread_id)
    if tenant_id is None or tenant_id != context.tenant_id:
        raise HTTPException(status_code=404, detail="pending approval not found")
    try:
        _permissions.require(context, "report:review")
    except PermissionError as error:
        raise HTTPException(status_code=403, detail=str(error)) from error


@router.post("/assistant/{thread_id}/resume", response_model=AssistantInvokeResponse)
async def resume_assistant(
    thread_id: str, payload: AssistantResumeRequest, request: Request
) -> AssistantInvokeResponse:
    _require_pending_approval(thread_id, request)
    context = build_development_context(request, thread_id)
    result = await _graph.ainvoke(
        Command(resume=payload.model_dump()), {"configurable": {"thread_id": thread_id}}
    )
    _pending_approval_tenants.pop(thread_id, None)
    return AssistantInvokeResponse(
        request_id=context.request_id,
        thread_id=thread_id,
        intent=result["intent"],
        status=result["status"],
        message=result["result_message"],
        warnings=result["warnings"],
    )


@router.get("/assistant/{thread_id}/state", response_model=AssistantStateResponse)
async def assistant_state(thread_id: str, request: Request) -> AssistantStateResponse:
    _require_pending_approval(thread_id, request)
    snapshot = await _graph.aget_state({"configurable": {"thread_id": thread_id}})
    return AssistantStateResponse(
        thread_id=thread_id,
        status=str(snapshot.values.get("status", "unknown")),
        awaiting_approval=bool(snapshot.next),
        next_nodes=list(snapshot.next),
    )


@router.post("/reports/generate", response_model=ReportDraft)
async def generate_report(payload: ReportGenerateRequest, request: Request) -> ReportDraft:
    context = build_development_context(request, thread_id=f"report:new:{payload.report_date}")
    agent = _report_agent_for(request)
    events = payload.events or (await agent.collect_mock_events() if payload.use_mock_sources else [])
    return await agent.generate_daily(report_date=payload.report_date, events=events, context=context)


@router.post("/reports/{report_id}/review", response_model=ReportDraft)
async def review_report(report_id: str, payload: ReportReviewRequest, request: Request) -> ReportDraft:
    context = build_development_context(request, thread_id=f"report:{report_id}")
    try:
        return await _report_agent_for(request).review(report_id=report_id, approved=payload.approved, comment=payload.comment, context=context, permissions=_permissions, audit=_audit_for(request))
    except KeyError as error:
        raise HTTPException(status_code=404, detail="report not found") from error
    except PermissionError as error:
        raise HTTPException(status_code=403, detail=str(error)) from error


@router.post("/reports/{report_id}/submit", response_model=ReportSubmission)
async def submit_report(report_id: str, request: Request) -> ReportSubmission:
    context = build_development_context(request, thread_id=f"report:{report_id}")
    try:
        return await _report_agent_for(request).submit(
            report_id=report_id, context=context, connector=_report_connector,
            permissions=_permissions, audit=_audit_for(request),
        )
    except KeyError as error:
        raise HTTPException(status_code=404, detail="report not found") from error
    except PermissionError as error:
        raise HTTPException(status_code=403, detail=str(error)) from error
    except ValueError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error


@router.post("/meetings/{meeting_id}/minutes", response_model=MeetingMinutesDraft)
async def generate_minutes(meeting_id: str, payload: MeetingMinutesRequest) -> MeetingMinutesDraft:
    return await _meeting_agent.generate(meeting_id=meeting_id, title=payload.title, segments=payload.segments)


@router.post("/meetings/{meeting_id}/reviews", response_model=MeetingMinutesDraft)
async def review_minutes(meeting_id: str, payload: MeetingReviewRequest, request: Request) -> MeetingMinutesDraft:
    context = build_development_context(request, thread_id=f"meeting:{meeting_id}")
    try:
        return await _meeting_agent.review(meeting_id=meeting_id, approved=payload.approved, comment=payload.comment, context=context, permissions=_permissions, audit=_audit)
    except KeyError as error:
        raise HTTPException(status_code=404, detail="meeting minutes not found") from error
    except PermissionError as error:
        raise HTTPException(status_code=403, detail=str(error)) from error


@router.post("/meetings/{meeting_id}/send", response_model=MeetingEmailStatus)
async def send_minutes(meeting_id: str, request: Request) -> MeetingEmailStatus:
    context = build_development_context(request, thread_id=f"meeting:{meeting_id}")
    try:
        return await _meeting_agent.send(meeting_id=meeting_id, context=context, connector=_email_connector, permissions=_permissions, audit=_audit)
    except KeyError as error:
        raise HTTPException(status_code=404, detail="meeting minutes not found") from error
    except PermissionError as error:
        raise HTTPException(status_code=403, detail=str(error)) from error
    except ValueError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error


@router.post("/emails/polish", response_model=EmailPolishDraft)
async def polish_email(payload: EmailPolishRequest) -> EmailPolishDraft:
    return EmailPolishAgent().polish(subject=payload.subject, body=payload.body, attachments=payload.attachments)


@router.post("/analysis/run", response_model=DataAnalysisResult)
async def analyze_data(payload: DataAnalysisRequest) -> DataAnalysisResult:
    return DataAnalysisAgent().analyze(rows=payload.rows)


@router.post("/analysis/files/{file_id}", response_model=DataAnalysisResult)
async def analyze_uploaded_file(file_id: str) -> DataAnalysisResult:
    try:
        return DataAnalysisAgent().analyze(rows=await _files.get_rows(file_id))
    except KeyError as error:
        raise HTTPException(status_code=404, detail="file not found") from error


@router.post("/analysis/files/{file_id}/export")
async def export_uploaded_analysis(file_id: str) -> dict[str, str]:
    try:
        result = DataAnalysisAgent().analyze(rows=await _files.get_rows(file_id))
        return await _artifacts.export_analysis(result)
    except KeyError as error:
        raise HTTPException(status_code=404, detail="file not found") from error


@router.get("/files/{file_id}/metadata")
async def file_metadata(file_id: str) -> dict[str, object]:
    try:
        return (await _files.get_metadata(file_id)).as_dict()
    except KeyError as error:
        raise HTTPException(status_code=404, detail="file not found") from error


@router.post("/files/upload")
async def upload_file(file: UploadFile = File(...)) -> dict[str, str]:
    try:
        file_id = await _files.store_and_parse(
            filename=file.filename or "", content=await file.read(), content_type=file.content_type
        )
        return {"file_id": file_id, "status": "stored"}
    except (UnicodeDecodeError, UnsafeFileError) as error:
        raise HTTPException(status_code=422, detail=str(error)) from error


@router.delete("/files/{file_id}")
async def delete_file(file_id: str, request: Request) -> dict[str, str]:
    context = build_development_context(request, thread_id=f"file:{file_id}")
    try:
        _permissions.require(context, "file:delete")
        await _files.delete(file_id)
        await _audit_for(request).record(action="file.delete", context=context, target_id=file_id)
        return {"file_id": file_id, "status": "deleted"}
    except KeyError as error:
        raise HTTPException(status_code=404, detail="file not found") from error
    except PermissionError as error:
        raise HTTPException(status_code=403, detail=str(error)) from error
