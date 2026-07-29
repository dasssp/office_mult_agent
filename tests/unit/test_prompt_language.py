from app.orchestration.prompts import (
    DATA_PROMPT,
    EMAIL_PROMPT,
    GENERAL_PURPOSE_PROMPT,
    KNOWLEDGE_PROMPT,
    MAIN_AGENT_PROMPT,
    MEETING_PROMPT,
    REPORT_PROMPT,
)


def _contains_chinese(value: str) -> bool:
    return any("\u4e00" <= character <= "\u9fff" for character in value)


def test_agent_system_prompts_use_chinese() -> None:
    prompts = (
        MAIN_AGENT_PROMPT,
        GENERAL_PURPOSE_PROMPT,
        REPORT_PROMPT,
        MEETING_PROMPT,
        EMAIL_PROMPT,
        DATA_PROMPT,
        KNOWLEDGE_PROMPT,
    )
    assert all(_contains_chinese(prompt) for prompt in prompts)
