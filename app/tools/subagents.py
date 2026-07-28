from langchain_core.tools import tool

from app.agents.data_analysis_agent import DataAnalysisAgent
from app.agents.email_polish_agent import EmailPolishAgent
from app.agents.meeting_minutes_agent import MeetingMinutesAgent
from app.agents.report_agent import ReportAgent
from app.schemas import RequestContext


def build_subagent_tools(context: RequestContext | None = None):
    """Expose narrow, validated subagent operations to the Supervisor only."""

    @tool
    def email_polish_tool(subject: str, body: str) -> dict:
        """Produce an email draft. It never sends email."""
        return EmailPolishAgent().polish(subject=subject, body=body, attachments=[]).model_dump()

    @tool
    def data_analysis_tool(rows: list[dict[str, object]]) -> dict:
        """Compute deterministic tabular-data quality statistics."""
        return DataAnalysisAgent().analyze(rows=rows).model_dump()

    @tool
    async def meeting_minutes_tool(meeting_id: str, title: str, segments: list[dict[str, object]]) -> dict:
        """Create a meeting-minutes draft from supplied transcript segments."""
        from app.schemas.workflows import TranscriptSegment

        if context is None:
            raise ValueError("trusted request context is required")
        parsed = [TranscriptSegment.model_validate(item) for item in segments]
        # The supervisor tool creates drafts only; review/send remains in the API workflow.
        draft = await MeetingMinutesAgent().generate(
            meeting_id=meeting_id,
            title=title,
            segments=parsed,
            context=context,
        )
        return draft.model_dump()

    @tool
    async def report_draft_tool(
        report_date: str,
        events: list[dict[str, object]],
        report_type: str = "daily",
    ) -> dict:
        """Create an evidence-backed report draft. It never submits a report."""
        from app.schemas.workflows import WorkEvent

        parsed = [WorkEvent.model_validate(item) for item in events]
        agent = ReportAgent()
        if report_type == "weekly":
            return (
                await agent.generate_weekly(week_start=report_date, events=parsed)
            ).model_dump()
        return (
            await agent.generate_daily(report_date=report_date, events=parsed)
        ).model_dump()

    return [data_analysis_tool, email_polish_tool, meeting_minutes_tool, report_draft_tool]
