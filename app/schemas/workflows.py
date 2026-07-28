from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, Field


class WorkEvent(BaseModel):
    event_id: str
    title: str
    status: Literal["completed", "in_progress", "blocked", "planned", "unknown"]
    evidence_url: str | None = None


class ReportGenerateRequest(BaseModel):
    report_date: str
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


class MeetingReviewRequest(BaseModel):
    approved: bool
    comment: str | None = Field(default=None, max_length=1000)


class MeetingEmailStatus(BaseModel):
    meeting_id: str
    message_id: str
    status: Literal["sent"]


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


class DataAnalysisRequest(BaseModel):
    rows: list[dict[str, object]]


class DataAnalysisResult(BaseModel):
    row_count: int
    columns: list[str]
    null_counts: dict[str, int]
    status: Literal["completed"]


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
