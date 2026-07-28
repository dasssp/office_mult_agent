from typing import TypedDict

from app.schemas import Intent, RequestContext


class SupervisorState(TypedDict, total=False):
    message: str
    task_input: dict[str, object]
    intent: Intent
    status: str
    result_message: str
    subagent_result: dict[str, object]
    warnings: list[str]
    approval_comment: str | None
    context: RequestContext
