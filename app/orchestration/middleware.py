from collections.abc import Awaitable, Callable, Sequence
from typing import Any

from langchain.agents.middleware import AgentMiddleware, ModelRequest, ModelResponse
from langchain_core.messages import AIMessage, BaseMessage, SystemMessage, ToolMessage
from langchain_core.tools import BaseTool


def count_tool_calls(messages: Sequence[BaseMessage], tool_name: str) -> int:
    return sum(
        1
        for message in messages
        if isinstance(message, AIMessage)
        for call in message.tool_calls
        if call.get("name") == tool_name
    )


def requires_replan(messages: Sequence[BaseMessage]) -> bool:
    """Detect a delegated failure that happened after the latest plan update."""
    latest_failure = -1
    latest_plan = -1
    failure_markers = (
        '"status": "failed"',
        '"status":"failed"',
        '"status": "blocked"',
        '"status":"blocked"',
        "timeout",
        "error_code",
    )
    for index, message in enumerate(messages):
        if isinstance(message, AIMessage) and any(
            call.get("name") == "write_todos" for call in message.tool_calls
        ):
            latest_plan = index
        if isinstance(message, ToolMessage):
            content = message.text.lower()
            if any(marker in content for marker in failure_markers):
                latest_failure = index
    return latest_failure > latest_plan


def _tool_name(tool: BaseTool | dict[str, Any]) -> str | None:
    if isinstance(tool, BaseTool):
        return tool.name
    name = tool.get("name")
    if isinstance(name, str):
        return name
    function = tool.get("function")
    if isinstance(function, dict) and isinstance(function.get("name"), str):
        return function["name"]
    return None


class PlanningBudgetMiddleware(AgentMiddleware):
    """Enforce delegation budgets and replan-before-retry semantics."""

    def __init__(
        self,
        *,
        max_delegations: int,
        max_plan_updates: int,
    ) -> None:
        if max_delegations < 1 or max_plan_updates < 1:
            raise ValueError("agent budgets must be positive")
        self.max_delegations = max_delegations
        self.max_plan_updates = max_plan_updates

    def _limited_request(self, request: ModelRequest) -> ModelRequest:
        messages = request.messages
        delegation_count = count_tool_calls(messages, "task")
        plan_update_count = count_tool_calls(messages, "write_todos")
        exhausted: list[str] = []
        tools: list[BaseTool | dict[str, Any]] = list(request.tools)
        if delegation_count >= self.max_delegations:
            tools = [item for item in tools if _tool_name(item) != "task"]
            exhausted.append("子 Agent 委派")
        if plan_update_count >= self.max_plan_updates:
            tools = [
                item for item in tools if _tool_name(item) != "write_todos"
            ]
            exhausted.append("计划更新")
        if exhausted:
            notice = (
                "\n\n运行预算已耗尽：" + "、".join(exhausted) + "。"
                "不得继续调用对应工具；请基于已有结果返回 completed、partial 或 failed。"
            )
            system = request.system_message
            content = (system.text if system is not None else "") + notice
            return request.override(
                tools=tools,
                system_message=SystemMessage(content=content),
            )
        if requires_replan(messages):
            tools = [item for item in tools if _tool_name(item) != "task"]
            system = request.system_message
            content = (system.text if system is not None else "") + (
                "\n\n最近一次子任务返回 failed、blocked、timeout 或错误码。"
                "在继续委派前必须调用 write_todos：保留已完成项，标记失败项，"
                "补充替代步骤或明确终止条件。"
            )
            return request.override(
                tools=tools,
                system_message=SystemMessage(content=content),
            )
        return request

    def wrap_model_call(
        self,
        request: ModelRequest,
        handler: Callable[[ModelRequest], ModelResponse],
    ) -> ModelResponse:
        return handler(self._limited_request(request))

    async def awrap_model_call(
        self,
        request: ModelRequest,
        handler: Callable[[ModelRequest], Awaitable[ModelResponse]],
    ) -> ModelResponse:
        return await handler(self._limited_request(request))
