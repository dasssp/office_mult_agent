from uuid import uuid4

from fastapi import Request

from app.schemas import RequestContext


def build_development_context(request: Request, thread_id: str) -> RequestContext:
    """Development-only identity adapter; replace with verified auth in production."""
    return RequestContext(
        thread_id=thread_id,
        tenant_id=request.headers.get("x-tenant-id", "demo-tenant"),
        operator_id=request.headers.get("x-operator-id", "demo-operator"),
        employee_id=request.headers.get("x-employee-id", "demo-employee"),
        permission_scopes=set(request.headers.get("x-permission-scopes", "report:read").split(",")),
        trace_id=request.headers.get("x-trace-id", str(uuid4())),
    )
