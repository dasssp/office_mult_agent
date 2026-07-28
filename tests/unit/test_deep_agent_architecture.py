from collections.abc import Iterator
from typing import Any

import pytest
from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langchain_core.runnables import Runnable
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.store.memory import InMemoryStore

from app.agents.data_analysis_agent import DataAnalysisAgent
from app.agents.email_polish_agent import EmailPolishAgent
from app.agents.knowledge_agent import KnowledgeAgent
from app.agents.meeting_minutes_agent import MeetingMinutesAgent
from app.agents.report_agent import ReportAgent
from app.connectors.mocks.email import MockEmailConnector
from app.connectors.mocks.enterprise import (
    MockASRService,
    MockGitLabConnector,
    MockMeetingIMConnector,
    MockTaskConnector,
)
from app.connectors.mocks.report_system import MockReportSystemConnector
from app.orchestration import DeepAgentDependencies, DeepAgentRuntime, build_main_deep_agent
from app.orchestration.domain_graphs import build_report_subgraph
from app.orchestration.middleware import count_tool_calls, requires_replan
from app.orchestration.subagents import build_subagent_profiles
from app.schemas import RequestContext
from app.services.artifacts import ArtifactService
from app.services.audit import AuditService
from app.services.files import FileService
from app.services.permissions import PermissionService
from app.services.runtime_state import BackgroundTaskService, MemoryService


class ToolCallingFakeChatModel(GenericFakeChatModel):
    def bind_tools(
        self,
        tools: Any,
        *,
        tool_choice: str | None = None,
        **kwargs: Any,
    ) -> Runnable:
        return self


def _model() -> GenericFakeChatModel:
    messages: Iterator[AIMessage | str] = iter([AIMessage(content="完成")])
    return GenericFakeChatModel(messages=messages)


def _structured_model() -> ToolCallingFakeChatModel:
    messages: Iterator[AIMessage | str] = iter(
        [
            AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "MainAgentResponse",
                        "args": {
                            "status": "completed",
                            "summary": "请求已完成",
                            "completed_tasks": [],
                            "evidence_refs": [],
                            "artifact_refs": [],
                            "warnings": [],
                        },
                        "id": "result-1",
                        "type": "tool_call",
                    }
                ],
            )
        ]
    )
    return ToolCallingFakeChatModel(messages=messages)


def _report_model(arguments: dict[str, Any]) -> ToolCallingFakeChatModel:
    messages: Iterator[AIMessage | str] = iter(
        [
            AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "ReportTaskSpec",
                        "args": arguments,
                        "id": "report-spec-1",
                        "type": "tool_call",
                    }
                ],
            )
        ]
    )
    return ToolCallingFakeChatModel(messages=messages)


def _dependencies(tmp_path) -> DeepAgentDependencies:
    return DeepAgentDependencies(
        report_agent=ReportAgent(),
        meeting_agent=MeetingMinutesAgent(),
        email_agent=EmailPolishAgent(),
        data_agent=DataAnalysisAgent(),
        knowledge_agent=KnowledgeAgent(),
        report_connector=MockReportSystemConnector(),
        email_connector=MockEmailConnector(),
        meeting_connector=MockMeetingIMConnector(),
        asr=MockASRService(),
        gitlab_connector=MockGitLabConnector(),
        task_connector=MockTaskConnector(),
        permissions=PermissionService(),
        audit=AuditService(),
        files=FileService(storage_dir=tmp_path / "uploads"),
        artifacts=ArtifactService(root=tmp_path / "artifacts"),
        memory=MemoryService(),
        background_tasks=BackgroundTaskService(),
    )


def test_subagents_have_isolated_tool_sets_and_write_interrupts(tmp_path) -> None:
    profiles = build_subagent_profiles(_model(), _dependencies(tmp_path))
    by_name = {profile["name"]: profile for profile in profiles}

    assert set(by_name) == {
        "general-purpose",
        "report-agent",
        "meeting-agent",
        "email-agent",
        "data-agent",
        "knowledge-agent",
    }
    assert by_name["general-purpose"]["tools"] == []
    report_nodes = set(by_name["report-agent"]["runnable"].get_graph().nodes)
    meeting_nodes = set(by_name["meeting-agent"]["runnable"].get_graph().nodes)
    assert {
        "parse_report_task",
        "draft_report",
        "review_report",
        "submit_report",
        "finalize_report",
    }.issubset(report_nodes)
    assert {
        "parse_meeting_task",
        "enqueue_transcription",
        "generate_minutes",
        "review_minutes",
        "send_minutes",
        "finalize_meeting",
    }.issubset(meeting_nodes)
    assert {tool.name for tool in by_name["email-agent"]["tools"]} == {
        "polish_email",
    }
    assert {tool.name for tool in by_name["data-agent"]["tools"]} == {
        "analyze_rows",
        "analyze_file",
        "export_analysis",
    }
    for profile in profiles:
        for domain_tool in profile.get("tools", []):
            assert "runtime" not in domain_tool.args


def test_main_deep_agent_contains_planning_and_delegation_middleware(tmp_path) -> None:
    graph = build_main_deep_agent(
        model=_model(),
        dependencies=_dependencies(tmp_path),
        checkpointer=InMemorySaver(),
    )

    nodes = set(graph.get_graph().nodes)
    assert "TodoListMiddleware.after_model" in nodes
    assert "tools" in nodes


def test_deep_runtime_adapts_structured_result_to_existing_api() -> None:
    runtime = DeepAgentRuntime(graph=object())
    result = runtime._adapt(
        {
            "messages": [
                HumanMessage(content="分析文件并生成日报"),
                AIMessage(content="分析和日报已经完成"),
            ],
            "todos": [{"content": "分析文件", "status": "completed"}],
            "files": {"/workspace/result.json": {}},
        }
    )

    assert result["intent"].value == "composite_task"
    assert result["status"] == "completed"
    assert result["result"]["files"] == ["/workspace/result.json"]


def test_write_tools_map_to_least_privilege_review_scopes() -> None:
    assert DeepAgentRuntime._required_scope(["submit_report"]) == "report:submit"
    assert (
        DeepAgentRuntime._required_scope(["send_meeting_minutes"])
        == "meeting:send"
    )
    assert (
        DeepAgentRuntime._required_scope(["submit_report", "send_meeting_minutes"])
        == "assistant:review"
    )


def test_planning_budget_counts_parallel_delegations() -> None:
    messages = [
        AIMessage(
            content="",
            tool_calls=[
                {
                    "name": "task",
                    "args": {"description": "分析", "subagent_type": "data-agent"},
                    "id": "task-1",
                    "type": "tool_call",
                },
                {
                    "name": "task",
                    "args": {"description": "检索", "subagent_type": "knowledge-agent"},
                    "id": "task-2",
                    "type": "tool_call",
                },
            ],
        )
    ]
    assert count_tool_calls(messages, "task") == 2
    assert count_tool_calls(messages, "write_todos") == 0


def test_failed_subtask_requires_plan_update_before_new_delegation() -> None:
    messages = [
        AIMessage(
            content="",
            tool_calls=[
                {
                    "name": "write_todos",
                    "args": {"todos": []},
                    "id": "plan-1",
                    "type": "tool_call",
                }
            ],
        ),
        ToolMessage(
            content='{"status": "failed", "error_code": "SOURCE_TIMEOUT"}',
            tool_call_id="task-1",
        ),
    ]
    assert requires_replan(messages) is True
    messages.append(
        AIMessage(
            content="",
            tool_calls=[
                {
                    "name": "write_todos",
                    "args": {"todos": []},
                    "id": "plan-2",
                    "type": "tool_call",
                }
            ],
        )
    )
    assert requires_replan(messages) is False


@pytest.mark.asyncio
async def test_report_compiled_subgraph_generates_evidence_draft(tmp_path) -> None:
    context = RequestContext(
        thread_id="report-subgraph",
        tenant_id="tenant-a",
        operator_id="user-a",
        employee_id="employee-a",
    )
    graph = build_report_subgraph(
        model=_report_model(
            {
                "operation": "draft",
                "report_date": "2026-07-28",
                "report_type": "daily",
                "events": [],
            }
        ),
        dependencies=_dependencies(tmp_path),
        checkpointer=InMemorySaver(),
    )

    result = await graph.ainvoke(
        {"messages": [HumanMessage(content="生成今天的日报")]},
        {"configurable": {"thread_id": "report-subgraph"}},
        context=context,
    )

    assert result["status"] == "completed"
    assert result["result"]["status"] == "draft"
    assert result["result"]["evidence_event_ids"]


@pytest.mark.asyncio
async def test_deep_runtime_smoke_invocation_with_structured_output(tmp_path) -> None:
    store = InMemoryStore()
    memory = MemoryService()
    graph = build_main_deep_agent(
        model=_structured_model(),
        dependencies=_dependencies(tmp_path),
        checkpointer=InMemorySaver(),
        store=store,
    )
    runtime = DeepAgentRuntime(graph=graph, memory=memory, store=store)
    context = RequestContext(
        thread_id="deep-smoke",
        tenant_id="tenant-a",
        operator_id="user-a",
    )

    result = await runtime.ainvoke(
        {"message": "你好", "task_input": {}},
        {"configurable": {"thread_id": "deep-smoke"}},
        context=context,
    )

    assert result["status"] == "completed"
    assert result["result_message"] == "请求已完成"


@pytest.mark.asyncio
async def test_confirmed_memory_is_synced_to_tenant_user_namespace() -> None:
    memory = MemoryService()
    store = InMemoryStore()
    context = RequestContext(
        thread_id="thread-1",
        tenant_id="tenant-a",
        operator_id="user-a",
    )
    await memory.remember(
        key="report_style",
        value="简洁",
        confirmed=True,
        context=context,
    )
    runtime = DeepAgentRuntime(graph=object(), memory=memory, store=store)

    await runtime._sync_confirmed_memory(context)

    item = await store.aget(
        ("office-multi-agent", "tenant-a", "user-a"),
        "/memories/confirmed.md",
    )
    assert item is not None
    assert "report_style: 简洁" in item.value["content"]
    assert (
        await store.aget(
            ("office-multi-agent", "tenant-b", "user-a"),
            "/memories/confirmed.md",
        )
        is None
    )
