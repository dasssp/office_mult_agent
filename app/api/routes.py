from fastapi import APIRouter, Request

from app.agents.supervisor import build_supervisor_graph
from app.middleware.context import build_development_context
from app.schemas import AssistantInvokeRequest, AssistantInvokeResponse
from app.schemas.workflows import (
    DataAnalysisRequest, DataAnalysisResult, EmailPolishDraft, EmailPolishRequest,
    MeetingMinutesDraft, MeetingMinutesRequest, ReportDraft, ReportGenerateRequest,
)
from app.agents.data_analysis_agent import DataAnalysisAgent
from app.agents.email_polish_agent import EmailPolishAgent
from app.agents.meeting_minutes_agent import MeetingMinutesAgent
from app.agents.report_agent import ReportAgent

router = APIRouter()
_graph = build_supervisor_graph()


@router.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@router.post("/assistant/invoke", response_model=AssistantInvokeResponse)
async def invoke_assistant(payload: AssistantInvokeRequest, request: Request) -> AssistantInvokeResponse:
    context = build_development_context(request, payload.thread_id)
    result = await _graph.ainvoke({"message": payload.message})
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
    return ReportAgent().generate_daily(report_date=payload.report_date, events=payload.events)


@router.post("/meetings/{meeting_id}/minutes", response_model=MeetingMinutesDraft)
async def generate_minutes(meeting_id: str, payload: MeetingMinutesRequest) -> MeetingMinutesDraft:
    return MeetingMinutesAgent().generate(meeting_id=meeting_id, title=payload.title, segments=payload.segments)


@router.post("/emails/polish", response_model=EmailPolishDraft)
async def polish_email(payload: EmailPolishRequest) -> EmailPolishDraft:
    return EmailPolishAgent().polish(subject=payload.subject, body=payload.body, attachments=payload.attachments)


@router.post("/analysis/run", response_model=DataAnalysisResult)
async def analyze_data(payload: DataAnalysisRequest) -> DataAnalysisResult:
    return DataAnalysisAgent().analyze(rows=payload.rows)
