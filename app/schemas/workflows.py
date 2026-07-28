from datetime import datetime
from enum import StrEnum
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, Field


class SourceType(StrEnum):
    IM = "im"
    EMAIL = "email"
    GIT = "git"
    TASK = "task"
    MEETING = "meeting"
    MANUAL = "manual"
    ANALYSIS = "analysis"


class EvidenceRef(BaseModel):
    source_type: SourceType
    source_id: str
    evidence_url: str | None = None
    segment_id: str | None = None
    confidence: float = Field(default=1.0, ge=0, le=1)


class WorkEvent(BaseModel):
    event_id: str
    title: str
    status: Literal["completed", "in_progress", "blocked", "planned", "unknown"]
    evidence_url: str | None = None
    event_type: Literal[
        "task_completed",
        "task_progress",
        "problem",
        "decision",
        "collaboration",
        "meeting",
        "code_change",
        "plan",
    ] = "task_progress"
    project_id: str | None = None
    description: str | None = None
    result: str | None = None
    progress: float | None = Field(default=None, ge=0, le=100)
    event_time: datetime | None = None
    source_type: SourceType = SourceType.MANUAL
    source_id: str | None = None
    confidence: float = Field(default=1.0, ge=0, le=1)
    sensitive: bool = False
    participants: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    evidence: list[EvidenceRef] = Field(default_factory=list)


class ReportGenerateRequest(BaseModel):
    report_date: str
    report_type: Literal["daily", "weekly"] = "daily"
    events: list[WorkEvent] = Field(default_factory=list)
    use_mock_sources: bool = False


class ReportDraft(BaseModel):
    report_id: str = Field(default_factory=lambda: str(uuid4()))
    report_date: str
    completed: list[str]
    in_progress: list[str]
    risks: list[str]
    evidence_event_ids: list[str]
    status: Literal["draft", "approved", "rejected", "submitted"]
    review_comment: str | None = None
    report_type: Literal["daily", "weekly"] = "daily"
    overview: str = ""
    plans: list[str] = Field(default_factory=list)
    coordination_items: list[str] = Field(default_factory=list)
    source_warnings: list[str] = Field(default_factory=list)
    version: int = Field(default=1, ge=1)


class ReportReviewRequest(BaseModel):
    approved: bool
    comment: str | None = Field(default=None, max_length=1000)


class ReportSubmission(BaseModel):
    report_id: str
    submission_id: str
    status: Literal["submitted"]


class TranscriptSegment(BaseModel):
    segment_id: str
    text: str
    speaker_id: str | None = None
    confidence: float = Field(ge=0, le=1)
    speaker_name: str | None = None
    start_ms: int | None = Field(default=None, ge=0)
    end_ms: int | None = Field(default=None, ge=0)
    language: str = "zh-CN"
    reviewed: bool = False


class MeetingMinutesRequest(BaseModel):
    title: str
    segments: list[TranscriptSegment]


class MeetingMinutesDraft(BaseModel):
    meeting_id: str
    title: str
    summary: str
    evidence_segment_ids: list[str]
    warnings: list[str]
    status: Literal["draft", "approved", "rejected", "sent"]
    review_comment: str | None = None
    participants: list[str] = Field(default_factory=list)
    topics: list[str] = Field(default_factory=list)
    decisions: list["MeetingDecision"] = Field(default_factory=list)
    action_items: list["ActionItem"] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
    open_questions: list[str] = Field(default_factory=list)
    version: int = Field(default=1, ge=1)
    content_sha256: str | None = None


class MeetingDecision(BaseModel):
    content: str
    evidence_segment_ids: list[str] = Field(min_length=1)


class ActionItem(BaseModel):
    content: str
    owner_id: str | None = None
    owner_name: str | None = None
    due_date: str | None = None
    status: Literal["open", "in_progress", "completed"] = "open"
    evidence_segment_ids: list[str] = Field(min_length=1)


class MeetingReviewRequest(BaseModel):
    approved: bool
    comment: str | None = Field(default=None, max_length=1000)


class MeetingEmailStatus(BaseModel):
    meeting_id: str
    message_id: str
    status: Literal["sent"]


class BackgroundTaskResponse(BaseModel):
    task_id: str
    kind: str
    status: Literal[
        "queued",
        "running",
        "retry_wait",
        "succeeded",
        "failed",
        "cancelled",
    ]
    progress: int = Field(ge=0, le=100)
    attempts: int = Field(ge=0)
    max_attempts: int = Field(ge=1)
    cancel_requested: bool
    result: dict[str, object] | None = None
    error_code: str | None = None


class EmailPolishRequest(BaseModel):
    subject: str
    body: str
    attachments: list[str] = Field(default_factory=list)


class EmailPolishDraft(BaseModel):
    subject: str
    body: str
    warnings: list[str]
    send_ready: bool
    status: Literal["draft"]
    email_type: str = "general"
    primary_intent: str = "inform"
    expected_action: str | None = None
    sensitivity: Literal["public", "internal", "sensitive", "restricted"] = "internal"
    issues: list[str] = Field(default_factory=list)
    changes: list[str] = Field(default_factory=list)
    factual_consistency: bool = True


class DataAnalysisRequest(BaseModel):
    rows: list[dict[str, object]]


class DataAnalysisResult(BaseModel):
    row_count: int
    columns: list[str]
    null_counts: dict[str, int]
    status: Literal["completed"]
    numeric_summary: dict[str, dict[str, float]] = Field(default_factory=dict)
    duplicate_rows: int = 0
    quality_warnings: list[str] = Field(default_factory=list)
    source_file_id: str | None = None
    analysis_spec: dict[str, object] = Field(default_factory=dict)


class KnowledgeCitation(BaseModel):
    document_id: str
    chunk_id: str
    title: str


class KnowledgeAnswer(BaseModel):
    answer: str
    citations: list[KnowledgeCitation]
    warnings: list[str] = Field(default_factory=list)
    status: Literal["completed", "insufficient_evidence"]


class KnowledgeQueryRequest(BaseModel):
    query: str = Field(min_length=1, max_length=4000)
