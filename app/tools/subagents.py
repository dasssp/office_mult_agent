from langchain_core.tools import tool

from app.agents.data_analysis_agent import DataAnalysisAgent
from app.agents.email_polish_agent import EmailPolishAgent
from app.agents.meeting_minutes_agent import MeetingMinutesAgent
from app.agents.report_agent import ReportAgent
from app.schemas import RequestContext


def build_subagent_tools(context: RequestContext | None = None):
    """仅向 Supervisor 暴露范围受限且经过校验的子 Agent 操作。"""

    @tool
    def email_polish_tool(subject: str, body: str) -> dict:
        """生成邮件草稿，不会发送邮件。"""
        return EmailPolishAgent().polish(subject=subject, body=body, attachments=[]).model_dump()

    @tool
    def data_analysis_tool(rows: list[dict[str, object]]) -> dict:
        """计算确定性的表格数据质量统计信息。"""
        return DataAnalysisAgent().analyze(rows=rows).model_dump()

    @tool
    async def meeting_minutes_tool(meeting_id: str, title: str, segments: list[dict[str, object]]) -> dict:
        """根据提供的转写片段生成会议纪要草稿。"""
        from app.schemas.workflows import TranscriptSegment

        if context is None:
            raise ValueError("trusted request context is required")
        parsed = [TranscriptSegment.model_validate(item) for item in segments]
        # Supervisor 工具只生成草稿；审核和发送仍由 API 工作流负责。
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
        """生成有证据支撑的报告草稿，不会提交报告。"""
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
