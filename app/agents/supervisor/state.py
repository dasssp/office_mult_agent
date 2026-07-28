from typing import TypedDict

from app.schemas import Intent


class SupervisorState(TypedDict, total=False):
    message: str
    intent: Intent
    status: str
    result_message: str
    subagent_result: dict[str, object]
    warnings: list[str]
