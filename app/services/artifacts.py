import csv
from io import StringIO
from pathlib import Path
from uuid import uuid4

from app.schemas.workflows import DataAnalysisResult


class ArtifactService:
    def __init__(self, root: Path = Path("artifacts")) -> None:
        self.root = root

    async def export_analysis(self, result: DataAnalysisResult) -> dict[str, str]:
        self.root.mkdir(exist_ok=True)
        artifact_id = str(uuid4())
        csv_path = self.root / f"{artifact_id}.csv"
        svg_path = self.root / f"{artifact_id}.svg"
        buffer = StringIO()
        writer = csv.writer(buffer)
        writer.writerow(["column", "null_count"])
        writer.writerows(result.null_counts.items())
        csv_path.write_text(buffer.getvalue(), encoding="utf-8")
        width = 480
        bars = "".join(f'<text x="10" y="{40 + index * 32}">{name}: {count}</text><rect x="180" y="{24 + index * 32}" width="{count * 30}" height="16" fill="#2563eb" />' for index, (name, count) in enumerate(result.null_counts.items()))
        svg_path.write_text(f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{max(80, 40 + len(result.null_counts) * 32)}"><text x="10" y="18">Null counts</text>{bars}</svg>', encoding="utf-8")
        return {"artifact_id": artifact_id, "summary_csv": str(csv_path), "chart_svg": str(svg_path)}
