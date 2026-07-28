from typing import Protocol

from app.schemas import RequestContext


class ReportSystemConnector(Protocol):
    async def get_projects(self, *, context: RequestContext) -> list[dict]: ...

    async def get_work_types(self, *, context: RequestContext) -> list[dict]: ...

    async def get_report(
        self, *, report_id: str, context: RequestContext
    ) -> dict | None: ...

    async def submit_report(self, *, report: dict, idempotency_key: str, context: RequestContext) -> dict: ...

    async def update_report(
        self,
        *,
        report_id: str,
        report: dict,
        idempotency_key: str,
        context: RequestContext,
    ) -> dict: ...

    async def get_report_status(self, *, submission_id: str, context: RequestContext) -> dict: ...


class KnowledgeConnector(Protocol):
    async def answer(self, *, query: str, context: RequestContext) -> dict: ...


class EmailConnector(Protocol):
    async def send_email(
        self,
        *,
        subject: str,
        body: str,
        idempotency_key: str,
        context: RequestContext,
    ) -> dict[str, str]: ...

    async def get_send_status(
        self, *, message_id: str, context: RequestContext
    ) -> dict[str, str]: ...


class MeetingIMConnector(Protocol):
    async def get_meeting(
        self, *, meeting_id: str, context: RequestContext
    ) -> dict: ...

    async def get_invited_participants(
        self, *, meeting_id: str, context: RequestContext
    ) -> list[dict]: ...

    async def get_actual_participants(
        self, *, meeting_id: str, context: RequestContext
    ) -> list[dict]: ...

    async def get_recording(
        self, *, meeting_id: str, context: RequestContext
    ) -> dict: ...


class ASRService(Protocol):
    async def submit_transcription(
        self, *, recording_ref: str, context: RequestContext
    ) -> dict: ...

    async def get_transcription_status(
        self, *, task_id: str, context: RequestContext
    ) -> dict: ...

    async def get_transcription_result(
        self, *, task_id: str, context: RequestContext
    ) -> dict: ...


class GitConnector(Protocol):
    async def list_activity(
        self, *, employee_id: str, date_from: str, date_to: str, context: RequestContext
    ) -> list[dict]: ...


class TaskConnector(Protocol):
    async def list_tasks(
        self, *, employee_id: str, context: RequestContext
    ) -> list[dict]: ...


class DirectoryConnector(Protocol):
    async def get_employee(
        self, *, employee_id: str, context: RequestContext
    ) -> dict | None: ...

    async def search_employee(
        self, *, query: str, context: RequestContext
    ) -> list[dict]: ...
