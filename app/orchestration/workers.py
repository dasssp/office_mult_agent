from typing import cast

from deepagents.middleware.subagents import CompiledSubAgent, SubAgent
from langchain_core.language_models import BaseChatModel

from app.orchestration.prompts import (
    DATA_PROMPT,
    EMAIL_PROMPT,
    GENERAL_PURPOSE_PROMPT,
    KNOWLEDGE_PROMPT,
)
from app.orchestration.schemas import SubAgentOutcome
from app.orchestration.toolkit import (
    OrchestrationDependencies,
    build_data_tools,
    build_email_tools,
    build_knowledge_tools,
)
from app.orchestration.worker_graphs import (
    build_meeting_subgraph,
    build_report_subgraph,
)


def build_worker_profiles(
    model: BaseChatModel,
    deps: OrchestrationDependencies,
) -> list[SubAgent | CompiledSubAgent]:
    return cast(
        list[SubAgent | CompiledSubAgent],
        [
        {
            "name": "general-purpose",
            "description": "仅整理和汇总已经提供的内容，不执行领域业务。",
            "system_prompt": GENERAL_PURPOSE_PROMPT,
            "tools": [],
            "model": model,
            "response_format": SubAgentOutcome,
        },
        {
            "name": "report-agent",
            "description": (
                "可恢复报告领域子图：采集证据、生成日报周报、审核和幂等提交。"
            ),
            "runnable": build_report_subgraph(model=model, dependencies=deps),
        },
        {
            "name": "meeting-agent",
            "description": (
                "可恢复会议领域子图：生成纪要、人工审核和幂等发送。"
            ),
            "runnable": build_meeting_subgraph(model=model, dependencies=deps),
        },
        {
            "name": "email-agent",
            "description": "检查并润色邮件，默认只输出草稿。",
            "system_prompt": EMAIL_PROMPT,
            "tools": build_email_tools(deps),
            "model": model,
            "response_format": SubAgentOutcome,
        },
        {
            "name": "data-agent",
            "description": "分析受控表格或文件并导出可追溯图表和报告产物。",
            "system_prompt": DATA_PROMPT,
            "tools": build_data_tools(deps),
            "model": model,
            "response_format": SubAgentOutcome,
        },
        {
            "name": "knowledge-agent",
            "description": "通过 Java RAG MCP 检索企业知识并返回带引用答案。",
            "system_prompt": KNOWLEDGE_PROMPT,
            "tools": build_knowledge_tools(deps),
            "model": model,
            "response_format": SubAgentOutcome,
        },
        ],
    )
