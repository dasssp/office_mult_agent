from uuid import uuid4

from fastapi import HTTPException, Request

from app.config import get_settings
from app.schemas import RequestContext


def build_development_context(request: Request, thread_id: str) -> RequestContext:
    """Return gateway-injected identity; headers are accepted only outside production."""
    injected = getattr(request.state, "request_context", None)
    if isinstance(injected, RequestContext):
        return injected.model_copy(update={"thread_id": thread_id})
    if get_settings().app_env == "production":
        raise HTTPException(status_code=503, detail="trusted identity provider is not configured")
    return RequestContext(
        thread_id=thread_id,
        tenant_id=request.headers.get("x-tenant-id", "demo-tenant"),
        operator_id=request.headers.get("x-operator-id", "demo-operator"),
        employee_id=request.headers.get("x-employee-id", "demo-employee"),
        permission_scopes=set(request.headers.get("x-permission-scopes", "report:read").split(",")),
        trace_id=getattr(request.state, "request_id", request.headers.get("x-trace-id", str(uuid4()))),
    )
