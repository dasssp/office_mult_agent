from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.agents.report_agent import ReportAgent
from app.api.routes import router
from app.config import get_settings
from app.database import Database
from app.repositories.persistence import SqlAlchemyAuditRepository, SqlAlchemyReportRepository
from app.services.audit import AuditService

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    database = Database(settings.database_url) if settings.database_url else None
    if database is not None:
        app.state.report_agent = ReportAgent(SqlAlchemyReportRepository(database.session_factory))
        app.state.audit = AuditService(repository=SqlAlchemyAuditRepository(database.session_factory))
    try:
        yield
    finally:
        if database is not None:
            await database.dispose()


app = FastAPI(title=settings.app_name, lifespan=lifespan)
app.include_router(router)
