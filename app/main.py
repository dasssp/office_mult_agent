import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

from app.agents.knowledge_agent import KnowledgeAgent
from app.agents.report_agent import ReportAgent
from app.agents.supervisor import build_supervisor_graph
from app.api.routes import router
from app.config import get_settings
from app.connectors.mcp_knowledge import McpKnowledgeConnector
from app.database import Database
from app.middleware.runtime import RuntimeSecurityMiddleware
from app.repositories.persistence import (
    SqlAlchemyApprovalRepository,
    SqlAlchemyAuditRepository,
    SqlAlchemyReportRepository,
)
from app.services.approvals import ApprovalService
from app.services.audit import AuditService

settings = get_settings()
os.environ.setdefault("LANGGRAPH_STRICT_MSGPACK", "true")


@asynccontextmanager
async def lifespan(app: FastAPI):
    if settings.app_env == "production" and not settings.database_url:
        raise RuntimeError("DATABASE_URL is required in production")
    if settings.app_env == "production" and not settings.knowledge_mcp_url:
        raise RuntimeError("KNOWLEDGE_MCP_URL is required in production")
    database = Database(settings.database_url) if settings.database_url else None
    knowledge_agent = (
        KnowledgeAgent(McpKnowledgeConnector(settings.knowledge_mcp_url))
        if settings.knowledge_mcp_url
        else KnowledgeAgent()
    )
    app.state.knowledge_agent = knowledge_agent
    checkpointer_context = None
    if database is not None and settings.database_url is not None:
        app.state.database = database
        app.state.report_agent = ReportAgent(SqlAlchemyReportRepository(database.session_factory))
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
        app.state.graph = build_supervisor_graph(
            checkpointer=checkpointer, knowledge_agent=knowledge_agent
        )
    else:
        app.state.graph = build_supervisor_graph(
            checkpointer=InMemorySaver(), knowledge_agent=knowledge_agent
        )
    try:
        yield
    finally:
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
