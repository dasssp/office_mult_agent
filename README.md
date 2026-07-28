# Office Multi-Agent

企业内部多智能体办公助手，基于 FastAPI、LangGraph 与 PostgreSQL 构建。系统采用 Supervisor 编排四类专业 Agent：日报、会议纪要、邮件润色和文件分析；Java RAG 通过独立 MCP 适配层接入。

## 本地开发

```powershell
conda activate office-multi-agent
python -m pip install -e ".[dev]"
uvicorn app.main:app --reload
```

运行质量检查：

```powershell
pytest
ruff check .
mypy app
```

## 容器化交付

复制 `.env.example` 为 `.env`，替换其中的 `POSTGRES_PASSWORD`，然后启动本地交付环境：

```powershell
docker compose up --build -d
Invoke-RestMethod http://localhost:8000/ready
.\scripts\demo.ps1
```

镜像会在启动 Uvicorn 前执行 Alembic 迁移，并提供 `/health` 存活检查和 `/ready` 就绪检查。使用 `docker compose down` 停止服务；只有明确需要删除本地 PostgreSQL 数据和上传文件时，才应追加 `-v`。

## PostgreSQL 与工作流恢复

可先单独启动数据库：

```powershell
docker compose up -d postgres
```

在 `.env` 中设置 `DATABASE_URL` 为 asyncpg 连接串后，执行版本化迁移：

```powershell
alembic upgrade head
```

生产模式使用 `AsyncPostgresSaver` 保存 LangGraph 工作流检查点，可在审批中断后恢复；请求身份上下文不会写入检查点。业务数据表按租户隔离，包含报告、审计、审批、幂等、确认记忆、后台任务与调度记录。

## 人工审批

调用 `POST /assistant/invoke` 时传入 `require_approval: true`，报告草稿会在任何外部写操作前中断，并返回 `awaiting_approval`。具备 `report:review` 权限的操作人可调用 `POST /assistant/{thread_id}/resume` 并传入：

```json
{"approved": true, "comment": "审核通过"}
```

`GET /assistant/{thread_id}/state` 仅向同一租户返回待审批状态。审批记录在数据库模式下持久化，且只能被消费一次。

## Java RAG MCP

生产环境需要配置独立 Java RAG MCP 适配层地址：

```env
KNOWLEDGE_MCP_URL=http://knowledge-mcp-adapter:8001/mcp
KNOWLEDGE_MCP_SERVICE_TOKEN=请替换为服务间密钥
```

主应用使用 Streamable HTTP 调用 `knowledge_answer_tool`。生产模式缺少 `KNOWLEDGE_MCP_URL` 时会拒绝启动，避免误用开发 Mock。

## 生产安全要求

仅在配置下列条件后设置 `APP_ENV=production`：

- `DATABASE_URL`、`KNOWLEDGE_MCP_URL` 与 `KNOWLEDGE_MCP_SERVICE_TOKEN` 已配置；
- 网关注入可信的 `request.state.request_context`；
- 已接入密钥管理、对象存储、病毒扫描和生产级 DLP；
- 已替换 Mock 的报告、邮件、IM、任务及 Java RAG 连接器；
- 已建立 PostgreSQL 备份恢复、任务队列、调度执行器和可观测性平台。

开发环境可从请求头构造 Mock 身份；生产环境拒绝此方式。响应会返回请求标识和基础浏览器安全响应头；请求体受 `MAX_REQUEST_BODY_BYTES` 限制。敏感数据检测会在报告提交、会议纪要发送等外部写入前执行。

完整交付状态见 [docs/OPTIMIZATION_STATUS.md](docs/OPTIMIZATION_STATUS.md)。
