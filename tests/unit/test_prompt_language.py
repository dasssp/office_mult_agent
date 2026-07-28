from app.agents.data_analysis_agent.prompts import DATA_ANALYSIS_SYSTEM_PROMPT
from app.agents.email_polish_agent.prompts import EMAIL_SYSTEM_PROMPT
from app.agents.meeting_minutes_agent.prompts import MEETING_SYSTEM_PROMPT
from app.agents.report_agent.prompts import REPORT_SYSTEM_PROMPT
from app.agents.supervisor.prompts import SUPERVISOR_SYSTEM_PROMPT
from app.tools.subagents import build_subagent_tools


def _contains_chinese(value: str) -> bool:
    return any("\u4e00" <= character <= "\u9fff" for character in value)


def test_agent_system_prompts_use_chinese() -> None:
    prompts = (
        REPORT_SYSTEM_PROMPT,
        MEETING_SYSTEM_PROMPT,
        EMAIL_SYSTEM_PROMPT,
        DATA_ANALYSIS_SYSTEM_PROMPT,
        SUPERVISOR_SYSTEM_PROMPT,
    )
    assert all(_contains_chinese(prompt) for prompt in prompts)


def test_legacy_subagent_tool_descriptions_use_chinese() -> None:
    descriptions = [tool.description for tool in build_subagent_tools()]
    assert all(description is not None and _contains_chinese(description) for description in descriptions)
