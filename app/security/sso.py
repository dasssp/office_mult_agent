from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Protocol

from app.schemas import RequestContext

_request_sso_token: ContextVar[str | None] = ContextVar(
    "request_sso_token",
    default=None,
)


class InvalidSsoTokenError(ValueError):
    """The inbound Authorization header is not a usable Bearer token."""


class SsoTokenUnavailableError(RuntimeError):
    """The current request has no delegated SSO token for Java RAG."""


class SsoTokenProvider(Protocol):
    async def get_access_token(self, context: RequestContext) -> str: ...


def extract_bearer_token(authorization: str | None) -> str | None:
    if authorization is None:
        return None
    scheme, separator, token = authorization.partition(" ")
    token = token.strip()
    if (
        separator != " "
        or scheme.lower() != "bearer"
        or not token
        or len(token) > 8192
        or any(character.isspace() or ord(character) < 32 for character in token)
    ):
        raise InvalidSsoTokenError("invalid bearer token")
    return token


@contextmanager
def bind_sso_access_token(token: str | None) -> Iterator[None]:
    """Bind a secret to the request context and always remove it afterward."""

    reset_token = _request_sso_token.set(token)
    try:
        yield
    finally:
        _request_sso_token.reset(reset_token)


class RequestSsoTokenProvider:
    """Returns the delegated token without copying it into agent state or tool arguments."""

    async def get_access_token(self, context: RequestContext) -> str:
        del context
        token = _request_sso_token.get()
        if token is None:
            raise SsoTokenUnavailableError("SSO token is required for knowledge queries")
        return token
