param(
    [string]$BaseUrl = "http://localhost:8000"
)

Invoke-RestMethod "$BaseUrl/health"

$payload = @{
    thread_id = "demo-report-1"
    message = "generate daily report"
    require_approval = $true
    task_input = @{
        report_date = "2026-07-28"
        events = @(@{ event_id = "demo-1"; title = "Demo delivery"; status = "completed" })
    }
} | ConvertTo-Json -Depth 5

Invoke-RestMethod "$BaseUrl/assistant/invoke" -Method Post -ContentType "application/json" -Body $payload
