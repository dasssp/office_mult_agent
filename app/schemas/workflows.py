from typing import Literal

from pydantic import BaseModel, Field


class WorkEvent(BaseModel):
    event_id: str
    title: str
    status: Literal["completed", "in_progress", "blocked", "planned", "unknown"]
    evidence_url: str | None = None


class ReportGenerateRequest(BaseModel):
    report_date: str
    events: list[WorkEvent]


class ReportDraft(BaseModel):
    report_date: str
    completed: list[str]
    in_progress: list[str]
    risks: list[str]
    evidence_event_ids: list[str]
    status: Literal["draft"]


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
    status: Literal["draft"]


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
