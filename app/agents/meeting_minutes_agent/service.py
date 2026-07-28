from app.connectors.mocks.email import MockEmailConnector
from app.schemas import RequestContext
from app.schemas.workflows import MeetingEmailStatus, MeetingMinutesDraft, TranscriptSegment
from app.services.audit import AuditService
from app.services.idempotency import IdempotencyService
from app.services.permissions import PermissionService
from app.services.sensitive_data import SensitiveDataService


class MeetingMinutesAgent:
    def __init__(self) -> None:
        self._drafts: dict[str, MeetingMinutesDraft] = {}
        self._sent: IdempotencyService[MeetingEmailStatus] = IdempotencyService()
        self._sensitive_data = SensitiveDataService()

    async def generate(self, *, meeting_id: str, title: str, segments: list[TranscriptSegment]) -> MeetingMinutesDraft:
        evidence_ids = [segment.segment_id for segment in segments]
        summary = " ".join(segment.text for segment in segments)
        warnings = [] if segments else ["没有可用的转写片段，无法生成有证据的纪要。"]
        draft = MeetingMinutesDraft(meeting_id=meeting_id, title=title, summary=summary, evidence_segment_ids=evidence_ids, warnings=warnings, status="draft")
        self._drafts[meeting_id] = draft
        return draft

    async def review(self, *, meeting_id: str, approved: bool, comment: str | None, context: RequestContext, permissions: PermissionService, audit: AuditService) -> MeetingMinutesDraft:
        permissions.require(context, "meeting:review")
        draft = self._drafts.get(meeting_id)
        if draft is None:
            raise KeyError(meeting_id)
        draft.status = "approved" if approved else "rejected"
        draft.review_comment = comment
        await audit.record(action="meeting_minutes.review", context=context, target_id=meeting_id)
        return draft

    async def send(self, *, meeting_id: str, context: RequestContext, connector: MockEmailConnector, permissions: PermissionService, audit: AuditService) -> MeetingEmailStatus:
        permissions.require(context, "meeting:send")
        existing = self._sent.get(meeting_id, context)
        if existing is not None:
            return existing
        draft = self._drafts.get(meeting_id)
        if draft is None:
            raise KeyError(meeting_id)
        if draft.status != "approved":
            raise ValueError("meeting minutes must be approved before sending")
        self._sensitive_data.require_shareable(f"{draft.title}\n{draft.summary}")
        sent = await connector.send_email(subject=draft.title, body=draft.summary, idempotency_key=f"{context.tenant_id}:{meeting_id}", context=context)
        draft.status = "sent"
        result = MeetingEmailStatus(meeting_id=meeting_id, message_id=sent["message_id"], status="sent")
        await audit.record(action="meeting_minutes.send", context=context, target_id=meeting_id)
        return self._sent.remember(meeting_id, result, context)
