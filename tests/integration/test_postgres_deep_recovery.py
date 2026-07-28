import os
from collections.abc import Iterator
from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest
from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.runnables import Runnable
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from langgraph.types import Command

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
from app.database import Database
from app.orchestration.domain_graphs import build_report_subgraph
from app.orchestration.tools import DeepAgentDependencies
from app.repositories.persistence import (
    SqlAlchemyAuditRepository,
    SqlAlchemyReportRepository,
)
from app.repositories.runtime import (
    SqlAlchemyIdempotencyRepository,
    SqlAlchemyRuntimeStateRepository,
)
from app.schemas import RequestContext
from app.schemas.workflows import ReportDraft
from app.services.artifacts import ArtifactService
from app.services.audit import AuditService
from app.services.files import FileService
from app.services.idempotency import IdempotencyService
from app.services.permissions import PermissionService
from app.services.runtime_state import BackgroundTaskService, MemoryService

pytestmark = pytest.mark.skipif(
    not os.getenv("TEST_DATABASE_URL"),
    reason="TEST_DATABASE_URL is required for PostgreSQL recovery tests",
)


class _ToolCallingModel(GenericFakeChatModel):
    def bind_tools(
        self,
        tools: Any,
        *,
        tool_choice: str | None = None,
        **kwargs: Any,
    ) -> Runnable:
        return self


def _report_model(report_id: str) -> _ToolCallingModel:
    messages: Iterator[AIMessage | str] = iter(
        [
            AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "ReportTaskSpec",
                        "args": {
                            "operation": "submit",
                            "report_id": report_id,
                        },
                        "id": "spec-1",
                        "type": "tool_call",
                    }
                ],
            )
        ]
    )
    return _ToolCallingModel(messages=messages)


def _dependencies(
    *,
    database: Database,
    report_connector: MockReportSystemConnector,
    tmp_path: Path,
) -> DeepAgentDependencies:
    runtime_repository = SqlAlchemyRuntimeStateRepository(database.session_factory)
    report_agent = ReportAgent(
        SqlAlchemyReportRepository(database.session_factory),
        idempotency=IdempotencyService(
            SqlAlchemyIdempotencyRepository(database.session_factory)
        ),
    )
    return DeepAgentDependencies(
        report_agent=report_agent,
        meeting_agent=MeetingMinutesAgent(),
        email_agent=EmailPolishAgent(),
        data_agent=DataAnalysisAgent(),
        knowledge_agent=KnowledgeAgent(),
        report_connector=report_connector,
        email_connector=MockEmailConnector(),
        meeting_connector=MockMeetingIMConnector(),
        asr=MockASRService(),
        gitlab_connector=MockGitLabConnector(),
        task_connector=MockTaskConnector(),
        permissions=PermissionService(),
        audit=AuditService(
            repository=SqlAlchemyAuditRepository(database.session_factory)
        ),
        files=FileService(storage_dir=tmp_path / "uploads"),
        artifacts=ArtifactService(root=tmp_path / "artifacts"),
        memory=MemoryService(runtime_repository),
        background_tasks=BackgroundTaskService(runtime_repository),
    )


@pytest.mark.asyncio
async def test_report_interrupt_resumes_after_process_restart(tmp_path: Path) -> None:
    database_url = os.environ["TEST_DATABASE_URL"]
    checkpoint_url = database_url.replace("postgresql+asyncpg://", "postgresql://")
    database = Database(database_url)
    report_id = str(uuid4())
    thread_id = f"pg-recovery-{uuid4()}"
    context = RequestContext(
        thread_id=thread_id,
        tenant_id=f"tenant-{uuid4()}",
        operator_id="reviewer-1",
        employee_id="employee-1",
        permission_scopes={"report:review", "report:submit"},
    )
    connector = MockReportSystemConnector()
    dependencies = _dependencies(
        database=database,
        report_connector=connector,
        tmp_path=tmp_path,
    )
    draft = ReportDraft(
        report_id=report_id,
        report_date="2026-07-28",
        completed=["implemented recovery"],
        in_progress=[],
        risks=[],
        evidence_event_ids=["event-1"],
        status="draft",
    )
    await dependencies.report_agent.repository.save(draft, context)
    await dependencies.report_agent.review(
        report_id=report_id,
        approved=True,
        comment=None,
        context=context,
        permissions=dependencies.permissions,
        audit=dependencies.audit,
    )
    config = {"configurable": {"thread_id": thread_id}}

    async with AsyncPostgresSaver.from_conn_string(checkpoint_url) as saver:
        await saver.setup()
        graph = build_report_subgraph(
            model=_report_model(report_id),
            dependencies=dependencies,
            checkpointer=saver,
        )
        interrupted = await graph.ainvoke(
            {"messages": [HumanMessage(content=f"提交报告 {report_id}")]},
            config,
            context=context,
        )
        assert "__interrupt__" in interrupted

    # A new saver and graph emulate a fresh process recovering only from PostgreSQL.
    restarted_dependencies = _dependencies(
        database=database,
        report_connector=connector,
        tmp_path=tmp_path,
    )
    async with AsyncPostgresSaver.from_conn_string(checkpoint_url) as restarted_saver:
        restarted_graph = build_report_subgraph(
            model=_report_model(report_id),
            dependencies=restarted_dependencies,
            checkpointer=restarted_saver,
        )
        resumed = await restarted_graph.ainvoke(
            Command(resume={"decisions": [{"type": "approve"}]}),
            config,
            context=context,
        )

    assert resumed["status"] == "completed"
    assert resumed["result"]["status"] == "submitted"
    persisted = await restarted_dependencies.report_agent.repository.get(
        report_id, context
    )
    assert persisted is not None
    assert persisted.status == "submitted"
    await database.dispose()
