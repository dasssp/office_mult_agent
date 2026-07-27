from app.schemas.workflows import EmailPolishDraft


class EmailPolishAgent:
    def polish(self, *, subject: str, body: str, attachments: list[str]) -> EmailPolishDraft:
        warnings: list[str] = []
        if "附件" in body and not attachments:
            warnings.append("正文提及附件，但未提供附件引用。")
        return EmailPolishDraft(subject=subject.strip(), body=body.strip(), warnings=warnings, send_ready=not warnings, status="draft")
