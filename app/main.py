from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.agents.report_agent import ReportAgent
from app.api.routes import router
from app.config import get_settings
from app.database import Database
from app.middleware.runtime import RuntimeSecurityMiddleware
from app.repositories.persistence import SqlAlchemyAuditRepository, SqlAlchemyReportRepository
from app.services.audit import AuditService

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    if settings.app_env == "production" and not settings.database_url:
        raise RuntimeError("DATABASE_URL is required in production")
    database = Database(settings.database_url) if settings.database_url else None
    if database is not None:
        app.state.database = database
        app.state.report_agent = ReportAgent(SqlAlchemyReportRepository(database.session_factory))
        app.state.audit = AuditService(repository=SqlAlchemyAuditRepository(database.session_factory))
    try:
        yield
    finally:
        if database is not None:
            await database.dispose()


app = FastAPI(title=settings.app_name, lifespan=lifespan)
app.add_middleware(RuntimeSecurityMiddleware, max_request_body_bytes=settings.max_request_body_bytes)


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    request_id = getattr(request.state, "request_id", "unknown")
    return JSONResponse(
        status_code=500,
        content={"detail": "internal server error", "request_id": request_id},
    )

app.include_router(router)
