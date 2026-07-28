import csv
import io
import json
from dataclasses import dataclass, field
from pathlib import Path
from tempfile import NamedTemporaryFile
from uuid import uuid4


class UnsafeFileError(ValueError):
    pass


@dataclass
class FileService:
    files: dict[str, list[dict[str, object]]] = field(default_factory=dict)
    max_bytes: int = 2 * 1024 * 1024

    async def store_and_parse(self, *, filename: str, content: bytes) -> str:
        if len(content) > self.max_bytes:
            raise UnsafeFileError("file exceeds maximum size")
        suffix = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
        if suffix not in {"csv", "json", "xlsx"}:
            raise UnsafeFileError("only CSV, JSON and XLSX are supported")
        if suffix == "xlsx":
            rows = self._parse_xlsx(content)
        else:
            text = content.decode("utf-8-sig")
            rows = self._parse_csv(text) if suffix == "csv" else self._parse_json(text)
        file_id = str(uuid4())
        self.files[file_id] = rows
        return file_id

    async def get_rows(self, file_id: str) -> list[dict[str, object]]:
        if file_id not in self.files:
            raise KeyError(file_id)
        return self.files[file_id]

    def _parse_csv(self, text: str) -> list[dict[str, object]]:
        rows = list(csv.DictReader(io.StringIO(text)))
        for row in rows:
            if any(isinstance(value, str) and value.startswith(("=", "+", "-", "@")) for value in row.values()):
                raise UnsafeFileError("CSV formula injection detected")
        return [dict(row) for row in rows]

    def _parse_json(self, text: str) -> list[dict[str, object]]:
        parsed = json.loads(text)
        if not isinstance(parsed, list) or not all(isinstance(row, dict) for row in parsed):
            raise UnsafeFileError("JSON must be an array of objects")
        return parsed

    def _parse_xlsx(self, content: bytes) -> list[dict[str, object]]:
        from openpyxl import load_workbook

        with NamedTemporaryFile(suffix=".xlsx", delete=False) as handle:
            handle.write(content)
            path = Path(handle.name)
        try:
            workbook = load_workbook(path, read_only=True, data_only=True, keep_vba=False)
            sheet = workbook.active
            values = list(sheet.iter_rows(values_only=True))
            if not values:
                return []
            headers = [str(value) if value is not None else "" for value in values[0]]
            if not all(headers) or len(set(headers)) != len(headers):
                raise UnsafeFileError("XLSX headers must be present and unique")
            result = [dict(zip(headers, row, strict=True)) for row in values[1:]]
            workbook.close()
            return result
        finally:
            path.unlink(missing_ok=True)
