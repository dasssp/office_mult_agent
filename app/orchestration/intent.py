from app.schemas import Intent


def classify_intent(message: str) -> Intent:
    """为 API 响应提供稳定的意图标签，不参与 Supervisor 的模型路由决策。"""

    text = message.lower()
    if ("提交" in text or "submit" in text) and (
        "日报" in text or "周报" in text or "report" in text
    ):
        return Intent.REPORT_SUBMISSION
    if ("审核" in text or "review" in text) and (
        "会议" in text or "meeting" in text
    ):
        return Intent.MEETING_REVIEW
    if "图表" in text or "chart" in text:
        return Intent.CHART_GENERATION
    if "导出" in text or "export" in text:
        return Intent.REPORT_EXPORT
    if "记忆" in text or "偏好" in text or "memory" in text:
        return Intent.MEMORY_MANAGEMENT
    if ("分析" in text or "analysis" in text) and (
        "日报" in text or "report" in text
    ):
        return Intent.COMPOSITE_TASK
    if "日报" in text or "daily report" in text:
        return Intent.DAILY_REPORT
    if "周报" in text or "weekly report" in text:
        return Intent.WEEKLY_REPORT
    if "会议纪要" in text or "meeting minutes" in text:
        return Intent.MEETING_MINUTES
    if "润色" in text or "polish" in text:
        return Intent.EMAIL_POLISH
    if "excel" in text or "csv" in text or "分析文件" in text:
        return Intent.FILE_ANALYSIS
    if "知识库" in text or "knowledge" in text:
        return Intent.KNOWLEDGE_QA
    return Intent.GENERAL_CHAT
