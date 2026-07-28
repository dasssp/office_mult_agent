from app.schemas.workflows import DataAnalysisResult


class DataAnalysisAgent:
    def analyze(self, *, rows: list[dict[str, object]]) -> DataAnalysisResult:
        columns = sorted({key for row in rows for key in row})
        null_counts = {column: sum(row.get(column) in (None, "") for row in rows) for column in columns}
        numeric_summary: dict[str, dict[str, float]] = {}
        for column in columns:
            values = [
                float(value)
                for row in rows
                if isinstance((value := row.get(column)), (int, float))
                and not isinstance(value, bool)
            ]
            if values:
                numeric_summary[column] = {
                    "count": float(len(values)),
                    "min": min(values),
                    "max": max(values),
                    "mean": sum(values) / len(values),
                }
        normalized = [repr(sorted(row.items())) for row in rows]
        duplicate_rows = len(normalized) - len(set(normalized))
        warnings = []
        if duplicate_rows:
            warnings.append(f"检测到 {duplicate_rows} 行重复数据，未自动删除。")
        if any(null_counts.values()):
            warnings.append("数据包含空值，未自动填充或删除。")
        return DataAnalysisResult(
            row_count=len(rows),
            columns=columns,
            null_counts=null_counts,
            numeric_summary=numeric_summary,
            duplicate_rows=duplicate_rows,
            quality_warnings=warnings,
            status="completed",
        )
