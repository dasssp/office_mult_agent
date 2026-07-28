from enum import StrEnum
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


class Intent(StrEnum):
    COMPOSITE_TASK = "composite_task"
    DAILY_REPORT = "daily_report"
    WEEKLY_REPORT = "weekly_report"
    MEETING_MINUTES = "meeting_minutes"
    EMAIL_POLISH = "email_polish"
    FILE_ANALYSIS = "file_analysis"
    KNOWLEDGE_QA = "knowledge_qa"
    GENERAL_CHAT = "general_chat"
    UNSUPPORTED = "unsupported"


class RequestContext(BaseModel):
    request_id: UUID = Field(default_factory=uuid4)
    thread_id: str
    tenant_id: str
    operator_id: str
    employee_id: str | None = None
    department_id: str | None = None
    role_ids: list[str] = Field(default_factory=list)
    permission_scopes: set[str] = Field(default_factory=set)
    locale: str = "zh-CN"
    timezone: str = "Asia/Shanghai"
    trace_id: str = Field(default_factory=lambda: str(uuid4()))


class AssistantInvokeRequest(BaseModel):
    thread_id: str = Field(min_length=1, max_length=128)
    message: str = Field(min_length=1, max_length=8000)
    task_input: dict[str, object] = Field(default_factory=dict)
    require_approval: bool = False


class AssistantInvokeResponse(BaseModel):
    request_id: UUID
    thread_id: str
    intent: Intent
    status: str
    message: str
    warnings: list[str] = Field(default_factory=list)
    awaiting_approval: bool = False


class AssistantResumeRequest(BaseModel):
    approved: bool
    comment: str | None = Field(default=None, max_length=1000)


class AssistantStateResponse(BaseModel):
    thread_id: str
    status: str
    awaiting_approval: bool
    next_nodes: list[str] = Field(default_factory=list)
