# Eight-point optimization status

Updated: 2026-07-28

## Implemented

1. **PostgreSQL workflow recovery**
   - Production uses `AsyncPostgresSaver`; schema setup runs during application startup.
   - `RequestContext` is runtime-only and is no longer serialized into checkpoints.
   - Strict LangGraph msgpack mode is enabled.
2. **Independent MCP knowledge boundary**
   - `McpKnowledgeConnector` invokes `knowledge_answer_tool` over Streamable HTTP.
   - `KNOWLEDGE_MCP_URL` selects the real connector; the local mock remains explicitly
     development-only.
3. **Tenant and identity controls**
   - Trusted runtime context is injected separately from LLM-controlled inputs.
   - File metadata, reads, analysis, export and deletion are tenant-scoped.
4. **Shared safety services**
   - Approval records are tenant-scoped and PostgreSQL-backed in database mode.
   - External report/meeting writes use a tenant-scoped idempotency service.
   - A replaceable sensitive-data guard blocks obvious credentials, identity numbers and
     phone numbers before external sharing.
5. **Persistence schema**
   - Migration `20260728_02` adds idempotency records, confirmed memory, background tasks
     and schedules.
6. **Business agents**
   - Report and meeting write paths enforce permission, approval, sensitive-data checks,
     idempotency and audit.
   - Email polishing and data analysis remain draft/read-only operations.
7. **Runtime foundations**
   - Confirmed-memory, background-task and five-field cron schedule services are present.
   - HTTP completion logs contain request ID, route, status and duration, never request body.
8. **Verification and delivery**
   - Unit and integration tests cover tenant isolation, approval single-use, idempotency,
     sensitive-data blocking, memory confirmation, task state and schedules.

## Deployment configuration

```env
DATABASE_URL=postgresql+asyncpg://office_app:password@postgres:5432/office_multi_agent
LANGGRAPH_STRICT_MSGPACK=true
KNOWLEDGE_MCP_URL=http://knowledge-mcp-adapter:8001/mcp
```

Run migrations before the API:

```bash
alembic upgrade head
```

## Explicit remaining production integrations

The repository does not claim that company systems are connected. Production still requires
company-provided authentication/gateway integration, Java RAG identity propagation and REST
contract, object storage and malware scanning, real report/email/IM/Git/task connectors, a
queue worker, a scheduler executor, a DLP service, secrets management, and an observability
backend. Current service boundaries and mocks are intended to let those integrations be added
without moving credentials or HTTP calls into Agent nodes.
