import pytest

from app.domain import DataAnalysisService, EmailPolishService, ReportService
from app.schemas.workflows import WorkEvent


@pytest.mark.asyncio
async def test_report_does_not_treat_plan_as_completed() -> None:
    draft = await ReportService().generate_daily(
        report_date="2026-07-28",
        events=[WorkEvent(event_id="1", title="准备发布", status="planned")],
    )
    assert draft.completed == []
    assert draft.evidence_event_ids == ["1"]


@pytest.mark.asyncio
async def test_weekly_report_deduplicates_events_and_preserves_evidence() -> None:
    events = [
        WorkEvent(
            event_id="1",
            title="完成接口",
            status="completed",
            project_id="p1",
            confidence=0.8,
        ),
        WorkEvent(
            event_id="2",
            title=" 完成接口 ",
            status="completed",
            project_id="p1",
            confidence=0.9,
        ),
    ]
    draft = await ReportService().generate_weekly(week_start="2026-07-27", events=events)
    assert draft.report_type == "weekly"
    assert draft.completed == [" 完成接口 "]
    assert draft.evidence_event_ids == ["2"]


def test_email_attachment_warning_blocks_send_readiness() -> None:
    draft = EmailPolishService().polish(subject="进度", body="附件请查收", attachments=[])
    assert not draft.send_ready


def test_data_analysis_reports_nulls() -> None:
    result = DataAnalysisService().analyze(rows=[{"amount": 1}, {"amount": None}])
    assert result.null_counts == {"amount": 1}
    assert result.numeric_summary["amount"]["mean"] == 1.0
    assert result.quality_warnings
