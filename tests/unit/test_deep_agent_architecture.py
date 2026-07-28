from collections.abc import Iterator
from typing import Any

import pytest
from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.messages import AIMessage, HumanMessage
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
    MockGitConnector,
    MockMeetingIMConnector,
    MockTaskConnector,
)
from app.connectors.mocks.report_system import MockReportSystemConnector
from app.orchestration import DeepAgentDependencies, DeepAgentRuntime, build_main_deep_agent
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
        git_connector=MockGitConnector(),
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
    assert {tool.name for tool in by_name["report-agent"]["tools"]} == {
        "collect_work_events",
        "generate_report_draft",
        "review_report",
        "submit_report",
    }
    assert {tool.name for tool in by_name["meeting-agent"]["tools"]} == {
        "get_meeting_context",
        "start_meeting_transcription",
        "get_meeting_transcription",
        "generate_meeting_minutes",
        "review_meeting_minutes",
        "send_meeting_minutes",
    }
    assert set(by_name["report-agent"]["interrupt_on"]) == {
        "review_report",
        "submit_report",
    }
    assert set(by_name["meeting-agent"]["interrupt_on"]) == {
        "review_meeting_minutes",
        "send_meeting_minutes",
    }
    for profile in profiles:
        for domain_tool in profile["tools"]:
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
