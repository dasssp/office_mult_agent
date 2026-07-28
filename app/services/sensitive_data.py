import re


class SensitiveDataError(ValueError):
    pass


class SensitiveDataService:
    """Small deterministic guard; production DLP can replace it behind this boundary."""

    _patterns = (
        re.compile(r"(?i)\b(password|passwd|token|api[_ -]?key)\s*[:=]\s*\S+"),
        re.compile(r"\b\d{17}[\dXx]\b"),
        re.compile(r"\b1[3-9]\d{9}\b"),
    )

    def findings(self, text: str) -> list[str]:
        labels = ("credential", "national_id", "phone")
        return [label for label, pattern in zip(labels, self._patterns, strict=True) if pattern.search(text)]

    def require_shareable(self, text: str) -> None:
        findings = self.findings(text)
        if findings:
            raise SensitiveDataError(
                f"external sharing blocked by sensitive-data policy: {', '.join(findings)}"
            )
