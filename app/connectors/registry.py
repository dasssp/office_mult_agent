from dataclasses import dataclass

from app.connectors.base import (
    ASRService,
    DirectoryConnector,
    EmailConnector,
    GitLabConnector,
    MeetingIMConnector,
    ReportSystemConnector,
    TaskConnector,
)
from app.connectors.gitlab import CachedGitLabConnector, GitLabHttpConnector
from app.connectors.mocks.email import MockEmailConnector
from app.connectors.mocks.enterprise import (
    MockASRService,
    MockDirectoryConnector,
    MockGitLabConnector,
    MockMeetingIMConnector,
    MockTaskConnector,
)
from app.connectors.mocks.report_system import MockReportSystemConnector
from app.schemas import RequestContext
from app.services.cache import JsonCache


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


class UnavailableGitLabConnector:
    async def list_activity(
        self,
        *,
        employee_id: str,
        date_from: str,
        date_to: str,
        context: RequestContext,
    ) -> list[dict]:
        raise ConnectorUnavailableError("GitLab connector is not configured")


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
    gitlab: GitLabConnector
    task: TaskConnector
    directory: DirectoryConnector

    @classmethod
    def for_environment(
        cls,
        app_env: str,
        *,
        gitlab_base_url: str | None = None,
        gitlab_access_token: str | None = None,
        gitlab_request_timeout_seconds: float = 10,
        cache: JsonCache | None = None,
        cache_key_prefix: str = "office-multi-agent",
        cache_ttl_seconds: int = 120,
    ) -> "ConnectorRegistry":
        if gitlab_base_url and gitlab_access_token:
            gitlab: GitLabConnector = GitLabHttpConnector(
                base_url=gitlab_base_url,
                access_token=gitlab_access_token,
                timeout_seconds=gitlab_request_timeout_seconds,
            )
        elif app_env == "production":
            gitlab = UnavailableGitLabConnector()
        else:
            gitlab = MockGitLabConnector()
        if cache is not None:
            gitlab = CachedGitLabConnector(
                gitlab,
                cache,
                key_prefix=cache_key_prefix,
                ttl_seconds=cache_ttl_seconds,
            )
        if app_env == "production":
            return cls(
                report_system=UnavailableReportSystemConnector(),
                email=UnavailableEmailConnector(),
                meeting_im=UnavailableMeetingIMConnector(),
                asr=UnavailableASRService(),
                gitlab=gitlab,
                task=UnavailableTaskConnector(),
                directory=UnavailableDirectoryConnector(),
            )
        return cls(
            report_system=MockReportSystemConnector(),
            email=MockEmailConnector(),
            meeting_im=MockMeetingIMConnector(),
            asr=MockASRService(),
            gitlab=gitlab,
            task=MockTaskConnector(),
            directory=MockDirectoryConnector(),
        )

    async def aclose(self) -> None:
        close = getattr(self.gitlab, "aclose", None)
        if close is not None:
            await close()
