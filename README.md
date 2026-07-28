# Office Multi-Agent

企业内部 Multi-Agent 办公助手。当前完成第一阶段的可运行基础工程：可信请求上下文、FastAPI、基础 LangGraph 路由、Mock Connector 和测试。

```powershell
conda activate office-multi-agent
python -m pip install -e ".[dev]"
uvicorn app.main:app --reload
pytest
```

## PostgreSQL

Start the local database with `docker compose up -d postgres`, then set `DATABASE_URL` to the asyncpg URL in `.env`. Apply the versioned schema before starting the API:

```powershell
alembic upgrade head
```

The current persistence boundary stores tenant-scoped report drafts and audit events. Database schema also reserves tables for agent threads/runs, approval tasks, and file metadata; uploaded source content remains outside the database and must be stored through an authorized object-storage connector.

## Human approval

Send `require_approval: true` to `POST /assistant/invoke` for a report task. The workflow pauses before any external write and returns `awaiting_approval`. An operator with `report:review` resumes the same checkpoint through `POST /assistant/{thread_id}/resume` with `{"approved": true|false, "comment": "..."}`. `GET /assistant/{thread_id}/state` exposes only the pending state for the same tenant.

开发环境会从请求头构造 Mock 身份；生产环境必须替换为已验证的认证提供方。
