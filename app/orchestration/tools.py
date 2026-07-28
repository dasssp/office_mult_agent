import asyncio
from dataclasses import dataclass
from typing import Any

from langchain.tools import ToolRuntime
from langchain_core.tools import BaseTool, tool

from app.agents.data_analysis_agent import DataAnalysisAgent
from app.agents.email_polish_agent import EmailPolishAgent
from app.agents.knowledge_agent import KnowledgeAgent
from app.agents.meeting_minutes_agent import MeetingMinutesAgent
from app.agents.report_agent import ReportAgent
from app.connectors.base import (
    ASRService,
    EmailConnector,
    GitLabConnector,
    MeetingIMConnector,
    ReportSystemConnector,
    TaskConnector,
)
from app.schemas import RequestContext
from app.schemas.workflows import TranscriptSegment, WorkEvent
from app.services.artifacts import ArtifactService
from app.services.audit import AuditService
from app.services.files import FileService
from app.services.permissions import PermissionService
from app.services.runtime_state import BackgroundTaskService, MemoryService
from app.services.work_events import MultiSourceWorkEventCollector


@dataclass
class DeepAgentDependencies:
    report_agent: ReportAgent
    meeting_agent: MeetingMinutesAgent
    email_agent: EmailPolishAgent
    data_agent: DataAnalysisAgent
    knowledge_agent: KnowledgeAgent
    report_connector: ReportSystemConnector
    email_connector: EmailConnector
    meeting_connector: MeetingIMConnector
    asr: ASRService
    gitlab_connector: GitLabConnector
    task_connector: TaskConnector
    permissions: PermissionService
    audit: AuditService
    files: FileService
    artifacts: ArtifactService
    memory: MemoryService
    background_tasks: BackgroundTaskService


def _json(model: Any) -> dict[str, Any]:
    return model.model_dump(mode="json")


def build_report_tools(deps: DeepAgentDependencies) -> list[BaseTool]:
    @tool
    async def collect_work_events(
        date_from: str,
        date_to: str,
        runtime: ToolRuntime[RequestContext],
    ) -> dict[str, Any]:
        """并行查询 GitLab、任务、已发送邮件和已审核会议纪要。"""
        collection = await MultiSourceWorkEventCollector(
            gitlab=deps.gitlab_connector,
            tasks=deps.task_connector,
            email=deps.email_connector,
            meeting_minutes=deps.meeting_agent,
        ).collect(
            date_from=date_from,
            date_to=date_to,
            context=runtime.context,
        )
        return collection.model_dump(mode="json")

    @tool
    async def generate_report_draft(
        report_date: str,
        events: list[dict[str, object]],
        report_type: str,
        runtime: ToolRuntime[RequestContext],
        source_warnings: list[str] | None = None,
    ) -> dict[str, Any]:
        """根据多数据源工作事件生成日报或周报草稿，不执行提交。"""
        parsed = [WorkEvent.model_validate(item) for item in events]
        if report_type == "weekly":
            result = await deps.report_agent.generate_weekly(
                week_start=report_date,
                events=parsed,
                source_warnings=source_warnings,
                context=runtime.context,
            )
        else:
            result = await deps.report_agent.generate_daily(
                report_date=report_date,
                events=parsed,
                source_warnings=source_warnings,
                context=runtime.context,
            )
        return _json(result)

    @tool
    async def review_report(
        report_id: str,
        approved: bool,
        comment: str | None,
        runtime: ToolRuntime[RequestContext],
    ) -> dict[str, Any]:
        """审核报告草稿；这是受控状态变更，必须由人工确认工具调用。"""
        return _json(
            await deps.report_agent.review(
                report_id=report_id,
                approved=approved,
                comment=comment,
                context=runtime.context,
                permissions=deps.permissions,
                audit=deps.audit,
            )
        )

    @tool
    async def submit_report(
        report_id: str,
        runtime: ToolRuntime[RequestContext],
    ) -> dict[str, Any]:
        """幂等提交已审核报告到报工系统；必须由人工确认工具调用。"""
        return _json(
            await deps.report_agent.submit(
                report_id=report_id,
                context=runtime.context,
                connector=deps.report_connector,
                permissions=deps.permissions,
                audit=deps.audit,
            )
        )

    return [collect_work_events, generate_report_draft, review_report, submit_report]


def build_meeting_tools(deps: DeepAgentDependencies) -> list[BaseTool]:
    @tool
    async def get_meeting_context(
        meeting_id: str,
        runtime: ToolRuntime[RequestContext],
    ) -> dict[str, Any]:
        """读取会议元数据和实际参会人，不读取或执行任意外部链接。"""
        meeting, invited, actual = await asyncio.gather(
            deps.meeting_connector.get_meeting(
                meeting_id=meeting_id,
                context=runtime.context,
            ),
            deps.meeting_connector.get_invited_participants(
                meeting_id=meeting_id,
                context=runtime.context,
            ),
            deps.meeting_connector.get_actual_participants(
                meeting_id=meeting_id,
                context=runtime.context,
            ),
        )
        return {"meeting": meeting, "invited": invited, "actual": actual}

    @tool
    async def start_meeting_transcription(
        meeting_id: str,
        runtime: ToolRuntime[RequestContext],
    ) -> dict[str, Any]:
        """为会议录音启动受控 ASR 后台任务，立即返回任务标识。"""
        tracked = await deps.background_tasks.create(
            kind="meeting_transcription",
            payload={"meeting_id": meeting_id},
            context=runtime.context,
        )
        return {"background_task_id": tracked.task_id, "status": tracked.status}

    @tool
    async def get_meeting_transcription(
        background_task_id: str,
        runtime: ToolRuntime[RequestContext],
    ) -> dict[str, Any]:
        """查询 ASR 长任务；完成后返回转写片段并更新租户级任务状态。"""
        task = await deps.background_tasks.get(
            background_task_id,
            runtime.context,
        )
        return {
            "status": task.status,
            "progress": task.progress,
            "result": task.result,
            "error_code": task.error_code,
        }

    @tool
    async def generate_meeting_minutes(
        meeting_id: str,
        title: str,
        segments: list[dict[str, object]],
        runtime: ToolRuntime[RequestContext],
    ) -> dict[str, Any]:
        """根据可信转写片段生成带证据引用的会议纪要草稿。"""
        parsed = [TranscriptSegment.model_validate(item) for item in segments]
        return _json(
            await deps.meeting_agent.generate(
                meeting_id=meeting_id,
                title=title,
                segments=parsed,
                context=runtime.context,
            )
        )

    @tool
    async def review_meeting_minutes(
        meeting_id: str,
        approved: bool,
        comment: str | None,
        runtime: ToolRuntime[RequestContext],
    ) -> dict[str, Any]:
        """审核会议纪要；必须由人工确认工具调用。"""
        return _json(
            await deps.meeting_agent.review(
                meeting_id=meeting_id,
                approved=approved,
                comment=comment,
                context=runtime.context,
                permissions=deps.permissions,
                audit=deps.audit,
            )
        )

    @tool
    async def send_meeting_minutes(
        meeting_id: str,
        runtime: ToolRuntime[RequestContext],
    ) -> dict[str, Any]:
        """幂等发送已审核会议纪要；必须由人工确认工具调用。"""
        return _json(
            await deps.meeting_agent.send(
                meeting_id=meeting_id,
                context=runtime.context,
                connector=deps.email_connector,
                permissions=deps.permissions,
                audit=deps.audit,
            )
        )

    return [
        get_meeting_context,
        start_meeting_transcription,
        get_meeting_transcription,
        generate_meeting_minutes,
        review_meeting_minutes,
        send_meeting_minutes,
    ]


def build_email_tools(deps: DeepAgentDependencies) -> list[BaseTool]:
    @tool
    def polish_email(
        subject: str,
        body: str,
        attachments: list[str],
    ) -> dict[str, Any]:
        """检查事实、附件和敏感信息并生成邮件草稿，不发送邮件。"""
        return _json(
            deps.email_agent.polish(
                subject=subject,
                body=body,
                attachments=attachments,
            )
        )

    return [polish_email]


def build_data_tools(deps: DeepAgentDependencies) -> list[BaseTool]:
    @tool
    def analyze_rows(rows: list[dict[str, object]]) -> dict[str, Any]:
        """使用确定性代码分析表格行的质量和数值统计。"""
        return _json(deps.data_agent.analyze(rows=rows))

    @tool
    async def analyze_file(
        file_id: str,
        runtime: ToolRuntime[RequestContext],
    ) -> dict[str, Any]:
        """读取当前租户的受控文件并执行确定性分析。"""
        result = deps.data_agent.analyze(
            rows=await deps.files.get_rows(file_id, runtime.context)
        )
        result.source_file_id = file_id
        return _json(result)

    @tool
    async def export_analysis(
        file_id: str,
        runtime: ToolRuntime[RequestContext],
    ) -> dict[str, Any]:
        """为当前租户生成可追溯的分析报告和图表产物。"""
        result = deps.data_agent.analyze(
            rows=await deps.files.get_rows(file_id, runtime.context)
        )
        result.source_file_id = file_id
        return await deps.artifacts.export_analysis(result, runtime.context)

    return [analyze_rows, analyze_file, export_analysis]


def build_knowledge_tools(deps: DeepAgentDependencies) -> list[BaseTool]:
    @tool
    async def answer_enterprise_knowledge(
        query: str,
        runtime: ToolRuntime[RequestContext],
    ) -> dict[str, Any]:
        """通过独立 Java RAG MCP 服务回答企业知识问题并返回引用。"""
        return _json(
            await deps.knowledge_agent.answer(
                query=query,
                context=runtime.context,
                permissions=deps.permissions,
            )
        )

    return [answer_enterprise_knowledge]


def build_main_tools(deps: DeepAgentDependencies) -> list[BaseTool]:
    @tool
    async def list_confirmed_memories(
        runtime: ToolRuntime[RequestContext],
    ) -> list[dict[str, str]]:
        """读取当前租户、当前用户已经明确确认的长期偏好。"""
        memories = await deps.memory.list_for(runtime.context)
        return [{"key": item.key, "value": item.value} for item in memories]

    return [list_confirmed_memories]
