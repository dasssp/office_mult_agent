import hashlib
from datetime import datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from app.connectors.base import EmailConnector
from app.repositories.meetings import (
    InMemoryMeetingMinutesRepository,
    MeetingMinutesRepository,
)
from app.schemas import RequestContext
from app.schemas.workflows import (
    ActionItem,
    MeetingDecision,
    MeetingEmailStatus,
    MeetingMinutesDraft,
    TranscriptSegment,
)
from app.services.audit import AuditService
from app.services.idempotency import IdempotencyService
from app.services.permissions import PermissionService
from app.services.sensitive_data import SensitiveDataService


class MeetingMinutesService:
    def __init__(
        self,
        repository: MeetingMinutesRepository | None = None,
        idempotency: IdempotencyService | None = None,
    ) -> None:
        self._repository = repository or InMemoryMeetingMinutesRepository()
        self._idempotency = idempotency or IdempotencyService()
        self._sensitive_data = SensitiveDataService()

    async def generate(
        self,
        *,
        meeting_id: str,
        title: str,
        segments: list[TranscriptSegment],
        context: RequestContext,
        meeting_date: str | None = None,
    ) -> MeetingMinutesDraft:
        try:
            generated_at = datetime.now(ZoneInfo(context.timezone))
        except ZoneInfoNotFoundError:
            generated_at = datetime.now().astimezone()
        evidence_ids = [segment.segment_id for segment in segments]
        summary = " ".join(segment.text for segment in segments)
        warnings = [] if segments else ["没有可用的转写片段，无法生成有证据的纪要。"]
        decisions = [
            MeetingDecision(content=segment.text, evidence_segment_ids=[segment.segment_id])
            for segment in segments
            if any(marker in segment.text for marker in ("决定", "决议", "确认"))
        ]
        action_items = [
            ActionItem(content=segment.text, evidence_segment_ids=[segment.segment_id])
            for segment in segments
            if any(marker in segment.text for marker in ("负责", "跟进", "完成"))
        ]
        if action_items:
            warnings.append("行动项负责人和截止日期需要人工确认。")
        low_confidence = [segment.segment_id for segment in segments if segment.confidence < 0.6]
        if low_confidence:
            warnings.append(f"低置信度转写片段：{', '.join(low_confidence)}")
        draft = MeetingMinutesDraft(
            meeting_id=meeting_id,
            title=title,
            summary=summary,
            evidence_segment_ids=evidence_ids,
            warnings=warnings,
            decisions=decisions,
            action_items=action_items,
            status="draft",
            meeting_date=meeting_date or generated_at.date().isoformat(),
            generated_at=generated_at,
        )
        return await self._repository.save(draft, context)

    async def list_for_report(
        self,
        *,
        date_from: str,
        date_to: str,
        context: RequestContext,
    ) -> list[MeetingMinutesDraft]:
        items = await self._repository.list_recent(context)
        return [
            item
            for item in items
            if item.status in {"approved", "sent"}
            and item.meeting_date is not None
            and date_from <= item.meeting_date <= date_to
        ]

    async def review(self, *, meeting_id: str, approved: bool, comment: str | None, context: RequestContext, permissions: PermissionService, audit: AuditService) -> MeetingMinutesDraft:
        permissions.require(context, "meeting:review")
        draft = await self._repository.get(meeting_id, context)
        if draft is None:
            raise KeyError(meeting_id)
        draft.status = "approved" if approved else "rejected"
        draft.review_comment = comment
        draft.version += 1
        if approved:
            draft.content_sha256 = hashlib.sha256(
                draft.model_dump_json(exclude={"content_sha256"}).encode("utf-8")
            ).hexdigest()
        await audit.record(action="meeting_minutes.review", context=context, target_id=meeting_id)
        return await self._repository.save(draft, context)

    async def send(self, *, meeting_id: str, context: RequestContext, connector: EmailConnector, permissions: PermissionService, audit: AuditService) -> MeetingEmailStatus:
        permissions.require(context, "meeting:send")
        existing = await self._idempotency.get(
            operation="meeting_minutes.send", key=meeting_id, context=context
        )
        if existing is not None:
            return MeetingEmailStatus.model_validate(existing)
        draft = await self._repository.get(meeting_id, context)
        if draft is None:
            raise KeyError(meeting_id)
        if draft.status != "approved":
            raise ValueError("meeting minutes must be approved before sending")
        self._sensitive_data.require_shareable(f"{draft.title}\n{draft.summary}")
        sent = await connector.send_email(subject=draft.title, body=draft.summary, idempotency_key=f"{context.tenant_id}:{meeting_id}", context=context)
        draft.status = "sent"
        await self._repository.save(draft, context)
        result = MeetingEmailStatus(meeting_id=meeting_id, message_id=sent["message_id"], status="sent")
        await audit.record(action="meeting_minutes.send", context=context, target_id=meeting_id)
        stored = await self._idempotency.remember(
            operation="meeting_minutes.send",
            key=meeting_id,
            result=result.model_dump(mode="json"),
            context=context,
        )
        return MeetingEmailStatus.model_validate(stored)
