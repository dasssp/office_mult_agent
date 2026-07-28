import asyncio
import csv
import hashlib
from html import escape
from io import StringIO
from pathlib import Path
from typing import Protocol
from uuid import uuid4

from app.schemas import RequestContext
from app.schemas.workflows import DataAnalysisResult


class ArtifactService:
    def __init__(
        self,
        root: Path = Path("artifacts"),
        repository: "ArtifactRepository | None" = None,
    ) -> None:
        self.root = root
        self.repository = repository

    async def export_analysis(
        self, result: DataAnalysisResult, context: RequestContext
    ) -> dict[str, str]:
        tenant_dir = self.root / hashlib.sha256(
            context.tenant_id.encode("utf-8")
        ).hexdigest()[:24]
        await asyncio.to_thread(tenant_dir.mkdir, parents=True, exist_ok=True)
        artifact_id = str(uuid4())
        csv_path = tenant_dir / f"{artifact_id}.csv"
        svg_path = tenant_dir / f"{artifact_id}.svg"
        buffer = StringIO()
        writer = csv.writer(buffer)
        writer.writerow(["column", "null_count"])
        writer.writerows(result.null_counts.items())
        await asyncio.to_thread(csv_path.write_text, buffer.getvalue(), encoding="utf-8")
        width = 480
        bars = "".join(
            f'<text x="10" y="{40 + index * 32}">{escape(name)}: {count}</text>'
            f'<rect x="180" y="{24 + index * 32}" width="{min(count, 1000) * 30}" '
            'height="16" fill="#2563eb" />'
            for index, (name, count) in enumerate(result.null_counts.items())
        )
        svg = (
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" '
            f'height="{max(80, 40 + len(result.null_counts) * 32)}">'
            f'<text x="10" y="18">空值数量</text>{bars}</svg>'
        )
        await asyncio.to_thread(svg_path.write_text, svg, encoding="utf-8")
        if self.repository is not None:
            await self.repository.save(
                artifact_id=artifact_id,
                kind="analysis_bundle",
                object_ref=str(tenant_dir),
                sha256=hashlib.sha256(
                    (buffer.getvalue() + svg).encode("utf-8")
                ).hexdigest(),
                context=context,
            )
        return {"artifact_id": artifact_id, "summary_csv": str(csv_path), "chart_svg": str(svg_path)}


class ArtifactRepository(Protocol):
    async def save(
        self,
        *,
        artifact_id: str,
        kind: str,
        object_ref: str,
        sha256: str,
        context: RequestContext,
    ) -> None: ...
