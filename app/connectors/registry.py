from dataclasses import dataclass

from app.connectors.base import (
    ASRService,
    DirectoryConnector,
    EmailConnector,
    GitConnector,
    MeetingIMConnector,
    ReportSystemConnector,
    TaskConnector,
)
from app.connectors.mocks.email import MockEmailConnector
from app.connectors.mocks.enterprise import (
    MockASRService,
    MockDirectoryConnector,
    MockGitConnector,
    MockMeetingIMConnector,
    MockTaskConnector,
)
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


class UnavailableMeetingIMConnector:
    async def get_meeting(self, *, meeting_id: str, context: RequestContext) -> dict:
        raise ConnectorUnavailableError("meeting IM connector is not configured")

    async def get_invited_participants(
        self, *, meeting_id: str, context: RequestContext
    ) -> list[dict]:
        raise ConnectorUnavailableError("meeting IM connector is not configured")

    async def get_actual_participants(
        self, *, meeting_id: str, context: RequestContext
    ) -> list[dict]:
        raise ConnectorUnavailableError("meeting IM connector is not configured")

    async def get_recording(
        self, *, meeting_id: str, context: RequestContext
    ) -> dict:
        raise ConnectorUnavailableError("meeting IM connector is not configured")


class UnavailableASRService:
    async def submit_transcription(
        self, *, recording_ref: str, context: RequestContext
    ) -> dict:
        raise ConnectorUnavailableError("ASR connector is not configured")

    async def get_transcription_status(
        self, *, task_id: str, context: RequestContext
    ) -> dict:
        raise ConnectorUnavailableError("ASR connector is not configured")

    async def get_transcription_result(
        self, *, task_id: str, context: RequestContext
    ) -> dict:
        raise ConnectorUnavailableError("ASR connector is not configured")


class UnavailableGitConnector:
    async def list_activity(
        self,
        *,
        employee_id: str,
        date_from: str,
        date_to: str,
        context: RequestContext,
    ) -> list[dict]:
        raise ConnectorUnavailableError("Git connector is not configured")


class UnavailableTaskConnector:
    async def list_tasks(
        self, *, employee_id: str, context: RequestContext
    ) -> list[dict]:
        raise ConnectorUnavailableError("task connector is not configured")


class UnavailableDirectoryConnector:
    async def get_employee(
        self, *, employee_id: str, context: RequestContext
    ) -> dict | None:
        raise ConnectorUnavailableError("directory connector is not configured")

    async def search_employee(
        self, *, query: str, context: RequestContext
    ) -> list[dict]:
        raise ConnectorUnavailableError("directory connector is not configured")


@dataclass(frozen=True)
class ConnectorRegistry:
    report_system: ReportSystemConnector
    email: EmailConnector
    meeting_im: MeetingIMConnector
    asr: ASRService
    git: GitConnector
    task: TaskConnector
    directory: DirectoryConnector

    @classmethod
    def for_environment(cls, app_env: str) -> "ConnectorRegistry":
        if app_env == "production":
            return cls(
                report_system=UnavailableReportSystemConnector(),
                email=UnavailableEmailConnector(),
                meeting_im=UnavailableMeetingIMConnector(),
                asr=UnavailableASRService(),
                git=UnavailableGitConnector(),
                task=UnavailableTaskConnector(),
                directory=UnavailableDirectoryConnector(),
            )
        return cls(
            report_system=MockReportSystemConnector(),
            email=MockEmailConnector(),
            meeting_im=MockMeetingIMConnector(),
            asr=MockASRService(),
            git=MockGitConnector(),
            task=MockTaskConnector(),
            directory=MockDirectoryConnector(),
        )
