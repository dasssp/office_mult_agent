from dataclasses import dataclass
from typing import Any

from langchain.tools import ToolRuntime
from langchain_core.tools import BaseTool, tool

from app.connectors.base import (
    ASRService,
    EmailConnector,
    GitLabConnector,
    MeetingIMConnector,
    ReportSystemConnector,
    TaskConnector,
)
from app.domain import (
    DataAnalysisService,
    EmailPolishService,
    KnowledgeService,
    MeetingMinutesService,
    ReportService,
)
from app.schemas import RequestContext
from app.services.artifacts import ArtifactService
from app.services.audit import AuditService
from app.services.files import FileService
from app.services.permissions import PermissionService
from app.services.runtime_state import BackgroundTaskService, MemoryService


@dataclass
class OrchestrationDependencies:
    report_service: ReportService
    meeting_service: MeetingMinutesService
    email_service: EmailPolishService
    data_analysis_service: DataAnalysisService
    knowledge_service: KnowledgeService
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


def build_email_tools(deps: OrchestrationDependencies) -> list[BaseTool]:
    @tool
    def polish_email(
        subject: str,
        body: str,
        attachments: list[str],
    ) -> dict[str, Any]:
        """检查事实、附件和敏感信息并生成邮件草稿，不发送邮件。"""
        return _json(
            deps.email_service.polish(
                subject=subject,
                body=body,
                attachments=attachments,
            )
        )

    return [polish_email]


def build_data_tools(deps: OrchestrationDependencies) -> list[BaseTool]:
    @tool
    def analyze_rows(rows: list[dict[str, object]]) -> dict[str, Any]:
        """使用确定性代码分析表格行的质量和数值统计。"""
        return _json(deps.data_analysis_service.analyze(rows=rows))

    @tool
    async def analyze_file(
        file_id: str,
        runtime: ToolRuntime[RequestContext],
    ) -> dict[str, Any]:
        """读取当前租户的受控文件并执行确定性分析。"""
        result = deps.data_analysis_service.analyze(
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
        result = deps.data_analysis_service.analyze(
            rows=await deps.files.get_rows(file_id, runtime.context)
        )
        result.source_file_id = file_id
        return await deps.artifacts.export_analysis(result, runtime.context)

    return [analyze_rows, analyze_file, export_analysis]


def build_knowledge_tools(deps: OrchestrationDependencies) -> list[BaseTool]:
    @tool
    async def answer_enterprise_knowledge(
        query: str,
        runtime: ToolRuntime[RequestContext],
    ) -> dict[str, Any]:
        """通过 Java RAG 提供的 MCP 服务回答企业知识问题并返回引用。"""
        return _json(
            await deps.knowledge_service.answer(
                query=query,
                context=runtime.context,
            )
        )

    return [answer_enterprise_knowledge]


def build_main_tools(deps: OrchestrationDependencies) -> list[BaseTool]:
    @tool
    async def list_confirmed_memories(
        runtime: ToolRuntime[RequestContext],
    ) -> list[dict[str, str]]:
        """读取当前租户、当前用户已经明确确认的长期偏好。"""
        memories = await deps.memory.list_for(runtime.context)
        return [{"key": item.key, "value": item.value} for item in memories]

    return [list_confirmed_memories]
