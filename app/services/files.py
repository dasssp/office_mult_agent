import csv
import io
import json
from dataclasses import dataclass, field
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
        if suffix not in {"csv", "json"}:
            raise UnsafeFileError("only CSV and JSON are supported in this phase")
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
