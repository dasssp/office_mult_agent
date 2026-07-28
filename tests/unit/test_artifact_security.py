from pathlib import Path

import pytest

from app.schemas import RequestContext
from app.schemas.workflows import DataAnalysisResult
from app.services.artifacts import ArtifactService


@pytest.mark.asyncio
async def test_svg_escapes_untrusted_column_names_and_uses_tenant_directory(
    tmp_path: Path,
) -> None:
    context = RequestContext(
        thread_id="artifact-1",
        tenant_id="../tenant-a",
        operator_id="operator-a",
    )
    result = DataAnalysisResult(
        row_count=1,
        columns=["<script>alert(1)</script>"],
        null_counts={"<script>alert(1)</script>": 1},
        status="completed",
    )
    exported = await ArtifactService(tmp_path).export_analysis(result, context)
    svg_path = Path(exported["chart_svg"])
    assert svg_path.parent.parent == tmp_path
    assert "<script>" not in svg_path.read_text(encoding="utf-8")
    assert "&lt;script&gt;" in svg_path.read_text(encoding="utf-8")
