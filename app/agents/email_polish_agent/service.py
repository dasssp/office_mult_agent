from app.schemas.workflows import EmailPolishDraft
from app.services.sensitive_data import SensitiveDataService


class EmailPolishAgent:
    def polish(self, *, subject: str, body: str, attachments: list[str]) -> EmailPolishDraft:
        warnings: list[str] = []
        issues: list[str] = []
        changes: list[str] = []
        if "附件" in body and not attachments:
            warnings.append("正文提及附件，但未提供附件引用。")
            issues.append("附件缺失")
        findings = SensitiveDataService().findings(body)
        if findings:
            warnings.append(f"检测到敏感信息：{', '.join(findings)}")
            issues.append("敏感信息")
        polished_subject = subject.strip()
        polished_body = "\n".join(line.rstrip() for line in body.strip().splitlines())
        if polished_subject != subject or polished_body != body:
            changes.append("清理首尾空白并统一行尾格式")
        email_type = "request" if any(word in body for word in ("请", "烦请", "需要")) else "notice"
        expected_action = "请收件人按正文要求处理" if email_type == "request" else None
        return EmailPolishDraft(
            subject=polished_subject,
            body=polished_body,
            warnings=warnings,
            send_ready=not warnings,
            status="draft",
            email_type=email_type,
            primary_intent="request_action" if email_type == "request" else "inform",
            expected_action=expected_action,
            sensitivity="sensitive" if findings else "internal",
            issues=issues,
            changes=changes,
            factual_consistency=True,
        )
