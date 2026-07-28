from fastapi import APIRouter, HTTPException, Request

from app.agents.data_analysis_agent import DataAnalysisAgent
from app.agents.email_polish_agent import EmailPolishAgent
from app.agents.meeting_minutes_agent import MeetingMinutesAgent
from app.agents.report_agent import ReportAgent
from app.agents.supervisor import build_supervisor_graph
from app.connectors.mocks.email import MockEmailConnector
from app.connectors.mocks.report_system import MockReportSystemConnector
from app.middleware.context import build_development_context
from app.schemas import AssistantInvokeRequest, AssistantInvokeResponse
from app.schemas.workflows import (
    DataAnalysisRequest,
    DataAnalysisResult,
    EmailPolishDraft,
    EmailPolishRequest,
    MeetingEmailStatus,
    MeetingMinutesDraft,
    MeetingMinutesRequest,
    MeetingReviewRequest,
    ReportDraft,
    ReportGenerateRequest,
    ReportReviewRequest,
    ReportSubmission,
)
from app.services.audit import AuditService
from app.services.permissions import PermissionService

router = APIRouter()
_graph = build_supervisor_graph()
_report_agent = ReportAgent()
_report_connector = MockReportSystemConnector()
_permissions = PermissionService()
_audit = AuditService()
_meeting_agent = MeetingMinutesAgent()
_email_connector = MockEmailConnector()


@router.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@router.post("/assistant/invoke", response_model=AssistantInvokeResponse)
async def invoke_assistant(payload: AssistantInvokeRequest, request: Request) -> AssistantInvokeResponse:
    context = build_development_context(request, payload.thread_id)
    result = await _graph.ainvoke({"message": payload.message, "task_input": payload.task_input})
    return AssistantInvokeResponse(
        request_id=context.request_id,
        thread_id=context.thread_id,
        intent=result["intent"],
        status=result["status"],
        message=result["result_message"],
        warnings=result["warnings"],
    )


@router.post("/reports/generate", response_model=ReportDraft)
async def generate_report(payload: ReportGenerateRequest) -> ReportDraft:
    events = payload.events or (await _report_agent.collect_mock_events() if payload.use_mock_sources else [])
    return await _report_agent.generate_daily(report_date=payload.report_date, events=events)


@router.post("/reports/{report_id}/review", response_model=ReportDraft)
async def review_report(report_id: str, payload: ReportReviewRequest, request: Request) -> ReportDraft:
    context = build_development_context(request, thread_id=f"report:{report_id}")
    try:
        return await _report_agent.review(report_id=report_id, approved=payload.approved, comment=payload.comment, context=context, permissions=_permissions, audit=_audit)
    except KeyError as error:
        raise HTTPException(status_code=404, detail="report not found") from error
    except PermissionError as error:
        raise HTTPException(status_code=403, detail=str(error)) from error


@router.post("/reports/{report_id}/submit", response_model=ReportSubmission)
async def submit_report(report_id: str, request: Request) -> ReportSubmission:
    context = build_development_context(request, thread_id=f"report:{report_id}")
    try:
        return await _report_agent.submit(
            report_id=report_id, context=context, connector=_report_connector,
            permissions=_permissions, audit=_audit,
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
async def review_minutes(meeting_id: str, payload: MeetingReviewRequest) -> MeetingMinutesDraft:
    try:
        return await _meeting_agent.review(meeting_id=meeting_id, approved=payload.approved, comment=payload.comment)
    except KeyError as error:
        raise HTTPException(status_code=404, detail="meeting minutes not found") from error


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
