import logging
import re
import time
from uuid import uuid4

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import JSONResponse, Response
from starlette.types import ASGIApp


class RuntimeSecurityMiddleware(BaseHTTPMiddleware):
    """Adds traceability and rejects oversized requests before parsing their bodies."""

    _request_id_pattern = re.compile(r"^[A-Za-z0-9_-]{8,128}$")

    def __init__(self, app: ASGIApp, max_request_body_bytes: int) -> None:
        super().__init__(app)
        self._max_request_body_bytes = max_request_body_bytes

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        started_at = time.perf_counter()
        content_length = request.headers.get("content-length")
        if content_length and content_length.isdigit() and int(content_length) > self._max_request_body_bytes:
            return JSONResponse(status_code=413, content={"detail": "request body too large"})
        supplied = request.headers.get("x-request-id", "")
        request.state.request_id = (
            supplied if self._request_id_pattern.fullmatch(supplied) else str(uuid4())
        )
        response = await call_next(request)
        response.headers["X-Request-ID"] = request.state.request_id
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Cache-Control"] = "no-store"
        logging.getLogger("office_multi_agent.http").info(
            "request_completed",
            extra={
                "request_id": request.state.request_id,
                "method": request.method,
                "path": request.url.path,
                "status_code": response.status_code,
                "duration_ms": round((time.perf_counter() - started_at) * 1000, 2),
            },
        )
        return response
