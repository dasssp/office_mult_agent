from app.schemas.workflows import DataAnalysisResult


class DataAnalysisAgent:
    def analyze(self, *, rows: list[dict[str, object]]) -> DataAnalysisResult:
        columns = sorted({key for row in rows for key in row})
        null_counts = {column: sum(row.get(column) in (None, "") for row in rows) for column in columns}
        return DataAnalysisResult(row_count=len(rows), columns=columns, null_counts=null_counts, status="completed")
