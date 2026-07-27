from app.schemas import RequestContext


class PermissionService:
    def require(self, context: RequestContext, scope: str) -> None:
        if scope not in context.permission_scopes:
            raise PermissionError(f"missing required permission: {scope}")
