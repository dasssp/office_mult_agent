from uuid import uuid4

from app.schemas import RequestContext


class MockMeetingIMConnector:
    async def get_meeting(self, *, meeting_id: str, context: RequestContext) -> dict:
        return {
            "meeting_id": meeting_id,
            "title": "项目周会",
            "host_id": "employee-a",
            "meeting_date": "2026-07-28",
        }

    async def get_invited_participants(
        self, *, meeting_id: str, context: RequestContext
    ) -> list[dict]:
        return [{"employee_id": "employee-a"}, {"employee_id": "employee-b"}]

    async def get_actual_participants(
        self, *, meeting_id: str, context: RequestContext
    ) -> list[dict]:
        return [{"employee_id": "employee-a"}, {"employee_id": "employee-b"}]

    async def get_recording(self, *, meeting_id: str, context: RequestContext) -> dict:
        return {"recording_ref": f"mock://recordings/{meeting_id}"}


class MockASRService:
    async def submit_transcription(
        self, *, recording_ref: str, context: RequestContext
    ) -> dict:
        return {"task_id": str(uuid4()), "status": "completed"}

    async def get_transcription_status(
        self, *, task_id: str, context: RequestContext
    ) -> dict:
        return {"task_id": task_id, "status": "completed"}

    async def get_transcription_result(
        self, *, task_id: str, context: RequestContext
    ) -> dict:
        return {
            "task_id": task_id,
            "segments": [
                {
                    "segment_id": "segment-1",
                    "text": "确认由项目组跟进发布",
                    "confidence": 0.95,
                }
            ],
        }


class MockGitLabConnector:
    async def list_activity(
        self,
        *,
        employee_id: str,
        date_from: str,
        date_to: str,
        context: RequestContext,
    ) -> list[dict]:
        return [
            {
                "type": "merge_request",
                "id": "mr-1",
                "title": "完成 GitLab 合并请求",
                "project_id": "project-demo",
            }
        ]


class MockTaskConnector:
    async def list_tasks(
        self, *, employee_id: str, context: RequestContext
    ) -> list[dict]:
        return [{"task_id": "task-1", "title": "完成接口实现", "status": "completed"}]


class MockDirectoryConnector:
    async def get_employee(
        self, *, employee_id: str, context: RequestContext
    ) -> dict | None:
        return {"employee_id": employee_id, "name": "演示员工", "email": "demo@example.invalid"}

    async def search_employee(
        self, *, query: str, context: RequestContext
    ) -> list[dict]:
        return [{"employee_id": "employee-a", "name": query}]
