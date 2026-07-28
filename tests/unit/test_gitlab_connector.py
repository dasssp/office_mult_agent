import httpx
import pytest

from app.connectors.gitlab import GitLabConnectorError, GitLabHttpConnector
from app.schemas import RequestContext


def _context() -> RequestContext:
    return RequestContext(
        thread_id="thread-1",
        tenant_id="tenant-a",
        operator_id="operator-a",
    )


@pytest.mark.asyncio
async def test_gitlab_connector_normalizes_contribution_events() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["PRIVATE-TOKEN"] == "secret-token"
        assert request.url.params["after"] == "2026-07-28"
        assert request.url.params["before"] == "2026-07-29"
        return httpx.Response(
            200,
            json=[
                {
                    "id": 7,
                    "action_name": "pushed to",
                    "target_type": None,
                    "project_id": 42,
                    "created_at": "2026-07-28T10:00:00Z",
                    "push_data": {"commit_title": "实现 Redis 缓存"},
                }
            ],
        )

    client = httpx.AsyncClient(
        base_url="https://gitlab.example/api/v4",
        transport=httpx.MockTransport(handler),
    )
    connector = GitLabHttpConnector(
        base_url="https://unused.example",
        access_token="secret-token",
        client=client,
    )
    result = await connector.list_activity(
        employee_id="developer-a",
        date_from="2026-07-28",
        date_to="2026-07-28",
        context=_context(),
    )

    assert result == [
        {
            "id": "7",
            "type": "pushed to",
            "title": "实现 Redis 缓存",
            "project_id": 42,
            "created_at": "2026-07-28T10:00:00Z",
        }
    ]
    await client.aclose()


@pytest.mark.asyncio
async def test_gitlab_connector_returns_sanitized_error() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, text="token secret-token rejected")

    client = httpx.AsyncClient(
        base_url="https://gitlab.example/api/v4",
        transport=httpx.MockTransport(handler),
    )
    connector = GitLabHttpConnector(
        base_url="https://unused.example",
        access_token="secret-token",
        client=client,
    )
    with pytest.raises(GitLabConnectorError, match="GitLab 活动查询失败") as error:
        await connector.list_activity(
            employee_id="developer-a",
            date_from="2026-07-28",
            date_to="2026-07-28",
            context=_context(),
        )
    assert "secret-token" not in str(error.value)
    await client.aclose()
