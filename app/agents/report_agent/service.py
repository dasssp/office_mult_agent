from app.schemas.workflows import ReportDraft, WorkEvent


class ReportAgent:
    def generate_daily(self, *, report_date: str, events: list[WorkEvent]) -> ReportDraft:
        completed = [event for event in events if event.status == "completed"]
        in_progress = [event for event in events if event.status == "in_progress"]
        blocked = [event for event in events if event.status == "blocked"]
        return ReportDraft(
            report_date=report_date,
            completed=[event.title for event in completed],
            in_progress=[event.title for event in in_progress],
            risks=[event.title for event in blocked],
            evidence_event_ids=[event.event_id for event in events],
            status="draft",
        )
