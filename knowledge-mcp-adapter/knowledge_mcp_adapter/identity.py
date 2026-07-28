from dataclasses import dataclass


@dataclass(frozen=True)
class TrustedIdentity:
    """Identity constructed by verified infrastructure, never by MCP tool input."""

    tenant_id: str
    employee_id: str

    def as_headers(self) -> dict[str, str]:
        if not self.tenant_id or not self.employee_id:
            raise PermissionError("trusted identity is required")
        return {"x-tenant-id": self.tenant_id, "x-employee-id": self.employee_id}


class MockTrustedIdentityProvider:
    """Development-only stand-in for the verified gateway context."""

    def get_identity(self) -> TrustedIdentity:
        return TrustedIdentity(tenant_id="demo-tenant", employee_id="demo-employee")
