from dataclasses import dataclass

from app.connectors.base import EmailConnector, ReportSystemConnector
from app.connectors.mocks.email import MockEmailConnector
from app.connectors.mocks.report_system import MockReportSystemConnector
from app.schemas import RequestContext


class ConnectorUnavailableError(RuntimeError):
    pass


class UnavailableReportSystemConnector:
    async def get_projects(self, *, context: RequestContext) -> list[dict]:
        raise ConnectorUnavailableError("report system connector is not configured")

    async def get_work_types(self, *, context: RequestContext) -> list[dict]:
        raise ConnectorUnavailableError("report system connector is not configured")

    async def get_report(
        self, *, report_id: str, context: RequestContext
    ) -> dict | None:
        raise ConnectorUnavailableError("report system connector is not configured")

    async def submit_report(
        self, *, report: dict, idempotency_key: str, context: RequestContext
    ) -> dict:
        raise ConnectorUnavailableError("report system connector is not configured")

    async def get_report_status(
        self, *, submission_id: str, context: RequestContext
    ) -> dict:
        raise ConnectorUnavailableError("report system connector is not configured")

    async def update_report(
        self,
        *,
        report_id: str,
        report: dict,
        idempotency_key: str,
        context: RequestContext,
    ) -> dict:
        raise ConnectorUnavailableError("report system connector is not configured")


class UnavailableEmailConnector:
    async def send_email(
        self,
        *,
        subject: str,
        body: str,
        idempotency_key: str,
        context: RequestContext,
    ) -> dict[str, str]:
        raise ConnectorUnavailableError("email connector is not configured")

    async def get_send_status(
        self, *, message_id: str, context: RequestContext
    ) -> dict[str, str]:
        raise ConnectorUnavailableError("email connector is not configured")


@dataclass(frozen=True)
class ConnectorRegistry:
    report_system: ReportSystemConnector
    email: EmailConnector

    @classmethod
    def for_environment(cls, app_env: str) -> "ConnectorRegistry":
        if app_env == "production":
            return cls(
                report_system=UnavailableReportSystemConnector(),
                email=UnavailableEmailConnector(),
            )
        return cls(
            report_system=MockReportSystemConnector(),
            email=MockEmailConnector(),
        )
