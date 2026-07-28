import pytest

from app.agents.data_analysis_agent import DataAnalysisAgent
from app.agents.email_polish_agent import EmailPolishAgent
from app.agents.report_agent import ReportAgent
from app.schemas.workflows import WorkEvent


@pytest.mark.asyncio
async def test_report_does_not_treat_plan_as_completed() -> None:
    draft = await ReportAgent().generate_daily(report_date="2026-07-28", events=[WorkEvent(event_id="1", title="准备发布", status="planned")])
    assert draft.completed == []
    assert draft.evidence_event_ids == ["1"]


def test_email_attachment_warning_blocks_send_readiness() -> None:
    draft = EmailPolishAgent().polish(subject="进度", body="附件请查收", attachments=[])
    assert not draft.send_ready


def test_data_analysis_reports_nulls() -> None:
    result = DataAnalysisAgent().analyze(rows=[{"amount": 1}, {"amount": None}])
    assert result.null_counts == {"amount": 1}
