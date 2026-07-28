from app.connectors.mocks.email import MockEmailConnector
from app.schemas import RequestContext
from app.schemas.workflows import MeetingEmailStatus, MeetingMinutesDraft, TranscriptSegment
from app.services.audit import AuditService
from app.services.permissions import PermissionService


class MeetingMinutesAgent:
    def __init__(self) -> None:
        self._drafts: dict[str, MeetingMinutesDraft] = {}
        self._sent: dict[str, MeetingEmailStatus] = {}

    async def generate(self, *, meeting_id: str, title: str, segments: list[TranscriptSegment]) -> MeetingMinutesDraft:
        evidence_ids = [segment.segment_id for segment in segments]
        summary = " ".join(segment.text for segment in segments)
        warnings = [] if segments else ["没有可用的转写片段，无法生成有证据的纪要。"]
        draft = MeetingMinutesDraft(meeting_id=meeting_id, title=title, summary=summary, evidence_segment_ids=evidence_ids, warnings=warnings, status="draft")
        self._drafts[meeting_id] = draft
        return draft

    async def review(self, *, meeting_id: str, approved: bool, comment: str | None) -> MeetingMinutesDraft:
        draft = self._drafts.get(meeting_id)
        if draft is None:
            raise KeyError(meeting_id)
        draft.status = "approved" if approved else "rejected"
        draft.review_comment = comment
        return draft

    async def send(self, *, meeting_id: str, context: RequestContext, connector: MockEmailConnector, permissions: PermissionService, audit: AuditService) -> MeetingEmailStatus:
        permissions.require(context, "meeting:send")
        if meeting_id in self._sent:
            return self._sent[meeting_id]
        draft = self._drafts.get(meeting_id)
        if draft is None:
            raise KeyError(meeting_id)
        if draft.status != "approved":
            raise ValueError("meeting minutes must be approved before sending")
        sent = await connector.send_email(subject=draft.title, body=draft.summary, idempotency_key=f"{context.tenant_id}:{meeting_id}", context=context)
        draft.status = "sent"
        result = MeetingEmailStatus(meeting_id=meeting_id, message_id=sent["message_id"], status="sent")
        self._sent[meeting_id] = result
        audit.record(action="meeting_minutes.send", context=context, target_id=meeting_id)
        return result
