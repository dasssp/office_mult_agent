import os
from contextlib import asynccontextmanager
from typing import cast

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from langchain.chat_models import init_chat_model
from langchain_core.language_models import BaseChatModel
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from langgraph.store.base import BaseStore
from langgraph.store.memory import InMemoryStore
from langgraph.store.postgres.aio import AsyncPostgresStore

from app.agents.data_analysis_agent import DataAnalysisAgent
from app.agents.email_polish_agent import EmailPolishAgent
from app.agents.knowledge_agent import KnowledgeAgent
from app.agents.meeting_minutes_agent import MeetingMinutesAgent
from app.agents.report_agent import ReportAgent
from app.agents.supervisor import build_supervisor_graph
from app.api.routes import router
from app.config import get_settings
from app.connectors.mcp_knowledge import McpKnowledgeConnector
from app.connectors.registry import ConnectorRegistry
from app.database import Database
from app.middleware.runtime import RuntimeSecurityMiddleware
from app.orchestration import DeepAgentDependencies, DeepAgentRuntime, build_main_deep_agent
from app.repositories.artifacts import SqlAlchemyArtifactRepository
from app.repositories.files import SqlAlchemyFileRepository
from app.repositories.meetings import SqlAlchemyMeetingMinutesRepository
from app.repositories.persistence import (
    SqlAlchemyApprovalRepository,
    SqlAlchemyAuditRepository,
    SqlAlchemyReportRepository,
)
from app.repositories.runtime import (
    SqlAlchemyIdempotencyRepository,
    SqlAlchemyRuntimeStateRepository,
)
from app.services.approvals import ApprovalService
from app.services.artifacts import ArtifactService
from app.services.audit import AuditService
from app.services.files import FileService
from app.services.idempotency import IdempotencyService
from app.services.permissions import PermissionService
from app.services.runtime_state import (
    BackgroundTaskService,
    MemoryService,
    ScheduleService,
)

settings = get_settings()
os.environ.setdefault("LANGGRAPH_STRICT_MSGPACK", "true")


@asynccontextmanager
async def lifespan(app: FastAPI):
    if settings.app_env == "production" and not settings.database_url:
        raise RuntimeError("DATABASE_URL is required in production")
    if settings.app_env == "production" and not settings.knowledge_mcp_url:
        raise RuntimeError("KNOWLEDGE_MCP_URL is required in production")
    if settings.app_env == "production" and not settings.knowledge_mcp_service_token:
        raise RuntimeError("KNOWLEDGE_MCP_SERVICE_TOKEN is required in production")
    if settings.assistant_runtime == "deep_agent" and not settings.agent_model:
        raise RuntimeError("AGENT_MODEL is required when ASSISTANT_RUNTIME=deep_agent")
    database = Database(settings.database_url) if settings.database_url else None
    knowledge_agent = (
        KnowledgeAgent(
            McpKnowledgeConnector(
                settings.knowledge_mcp_url,
                service_token=settings.knowledge_mcp_service_token,
            )
        )
        if settings.knowledge_mcp_url
        else KnowledgeAgent()
    )
    app.state.knowledge_agent = knowledge_agent
    app.state.connectors = ConnectorRegistry.for_environment(settings.app_env)
    checkpointer_context = None
    store_context = None
    store: BaseStore | None = None
    checkpointer: BaseCheckpointSaver
    if database is not None and settings.database_url is not None:
        app.state.database = database
        idempotency = IdempotencyService(
            SqlAlchemyIdempotencyRepository(database.session_factory)
        )
        runtime_repository = SqlAlchemyRuntimeStateRepository(database.session_factory)
        app.state.memory = MemoryService(runtime_repository)
        app.state.background_tasks = BackgroundTaskService(runtime_repository)
        app.state.schedules = ScheduleService(runtime_repository)
        app.state.files = FileService(
            repository=SqlAlchemyFileRepository(database.session_factory)
        )
        app.state.artifacts = ArtifactService(
            repository=SqlAlchemyArtifactRepository(database.session_factory)
        )
        app.state.report_agent = ReportAgent(
            SqlAlchemyReportRepository(database.session_factory),
            idempotency=idempotency,
        )
        app.state.meeting_agent = MeetingMinutesAgent(
            SqlAlchemyMeetingMinutesRepository(database.session_factory),
            idempotency=idempotency,
        )
        app.state.audit = AuditService(
            repository=SqlAlchemyAuditRepository(database.session_factory)
        )
        app.state.approvals = ApprovalService(
            repository=SqlAlchemyApprovalRepository(database.session_factory)
        )
        checkpoint_url = settings.database_url.replace("postgresql+asyncpg://", "postgresql://")
        checkpointer_context = AsyncPostgresSaver.from_conn_string(checkpoint_url)
        checkpointer = await checkpointer_context.__aenter__()
        await checkpointer.setup()
        if settings.assistant_runtime == "deep_agent":
            store_context = AsyncPostgresStore.from_conn_string(checkpoint_url)
            store = await store_context.__aenter__()
            await store.setup()
    else:
        checkpointer = InMemorySaver()
        store = InMemoryStore()
        app.state.memory = MemoryService()
        app.state.background_tasks = BackgroundTaskService()
        app.state.schedules = ScheduleService()
        app.state.files = FileService()
        app.state.artifacts = ArtifactService()
        app.state.report_agent = ReportAgent()
        app.state.meeting_agent = MeetingMinutesAgent()
        app.state.audit = AuditService()
        app.state.approvals = ApprovalService()

    if settings.assistant_runtime == "deep_agent":
        model = cast(BaseChatModel, init_chat_model(settings.agent_model))
        dependencies = DeepAgentDependencies(
            report_agent=app.state.report_agent,
            meeting_agent=app.state.meeting_agent,
            email_agent=EmailPolishAgent(),
            data_agent=DataAnalysisAgent(),
            knowledge_agent=knowledge_agent,
            report_connector=app.state.connectors.report_system,
            email_connector=app.state.connectors.email,
            meeting_connector=app.state.connectors.meeting_im,
            asr=app.state.connectors.asr,
            git_connector=app.state.connectors.git,
            task_connector=app.state.connectors.task,
            permissions=PermissionService(),
            audit=app.state.audit,
            files=app.state.files,
            artifacts=app.state.artifacts,
            memory=app.state.memory,
            background_tasks=app.state.background_tasks,
        )
        app.state.graph = DeepAgentRuntime(
            build_main_deep_agent(
                model=model,
                dependencies=dependencies,
                checkpointer=checkpointer,
                store=store,
                max_delegations=settings.agent_max_delegations,
                max_plan_updates=settings.agent_max_plan_updates,
            ),
            memory=app.state.memory,
            store=store,
            recursion_limit=settings.agent_recursion_limit,
            timeout_seconds=settings.agent_timeout_seconds,
        )
    else:
        app.state.graph = build_supervisor_graph(
            checkpointer=checkpointer, knowledge_agent=knowledge_agent
        )
    try:
        yield
    finally:
        if store_context is not None:
            await store_context.__aexit__(None, None, None)
        if checkpointer_context is not None:
            await checkpointer_context.__aexit__(None, None, None)
        if database is not None:
            await database.dispose()


app = FastAPI(title=settings.app_name, lifespan=lifespan)
app.add_middleware(
    RuntimeSecurityMiddleware, max_request_body_bytes=settings.max_request_body_bytes
)


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    request_id = getattr(request.state, "request_id", "unknown")
    return JSONResponse(
        status_code=500,
        content={"detail": "internal server error", "request_id": request_id},
    )


app.include_router(router)
