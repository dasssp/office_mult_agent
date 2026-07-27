from app.schemas.workflows import MeetingMinutesDraft, TranscriptSegment


class MeetingMinutesAgent:
    def generate(self, *, meeting_id: str, title: str, segments: list[TranscriptSegment]) -> MeetingMinutesDraft:
        evidence_ids = [segment.segment_id for segment in segments]
        summary = " ".join(segment.text for segment in segments)
        warnings = [] if segments else ["没有可用的转写片段，无法生成有证据的纪要。"]
        return MeetingMinutesDraft(meeting_id=meeting_id, title=title, summary=summary, evidence_segment_ids=evidence_ids, warnings=warnings, status="draft")
