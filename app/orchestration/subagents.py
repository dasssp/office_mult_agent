from typing import cast

from deepagents.middleware.subagents import SubAgent
from langchain_core.language_models import BaseChatModel

from app.orchestration.prompts import (
    DATA_PROMPT,
    EMAIL_PROMPT,
    GENERAL_PURPOSE_PROMPT,
    KNOWLEDGE_PROMPT,
    MEETING_PROMPT,
    REPORT_PROMPT,
)
from app.orchestration.schemas import SubAgentOutcome
from app.orchestration.tools import (
    DeepAgentDependencies,
    build_data_tools,
    build_email_tools,
    build_knowledge_tools,
    build_meeting_tools,
    build_report_tools,
)


def build_subagent_profiles(
    model: BaseChatModel,
    deps: DeepAgentDependencies,
) -> list[SubAgent]:
    return cast(
        list[SubAgent],
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
            "description": "生成、审核和受控提交日报或周报；处理工作事件与证据。",
            "system_prompt": REPORT_PROMPT,
            "tools": build_report_tools(deps),
            "model": model,
            "interrupt_on": {
                "review_report": {"allowed_decisions": ["approve", "reject"]},
                "submit_report": {"allowed_decisions": ["approve", "reject"]},
            },
            "response_format": SubAgentOutcome,
        },
        {
            "name": "meeting-agent",
            "description": "根据转写生成、审核并受控发送会议纪要。",
            "system_prompt": MEETING_PROMPT,
            "tools": build_meeting_tools(deps),
            "model": model,
            "interrupt_on": {
                "review_meeting_minutes": {
                    "allowed_decisions": ["approve", "reject"]
                },
                "send_meeting_minutes": {
                    "allowed_decisions": ["approve", "reject"]
                },
            },
            "response_format": SubAgentOutcome,
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
