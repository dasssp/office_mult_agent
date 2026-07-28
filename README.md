# Office Multi-Agent 企业办公助手

基于 FastAPI、LangGraph、Deep Agents 和 PostgreSQL 构建的企业级多智能体办公助手。
系统支持日报/周报、会议纪要、邮件润色、文件分析与图表导出、企业知识问答，并通过
独立 Java RAG MCP 适配层接入知识库。

## 架构亮点

- 一个主 Agent 负责任务理解、TODO 规划、并行委派、动态重规划和结果汇总。
- Report、Meeting 使用真实的可编译 LangGraph 领域子图；Email、Data、Knowledge
  使用隔离工具集的专业子 Agent。
- 子任务失败后强制先更新计划再继续委派，并限制委派次数、计划更新次数、递归深度和超时。
- Deep Agents 自动进行上下文摘要，大型中间产物卸载到工作区；确认后的长期记忆按
  `tenant_id + operator_id` 隔离保存。
- 报告审核/提交、会议纪要审核/发送通过 LangGraph `interrupt` 中断，使用 PostgreSQL
  Checkpointer 支持进程重启后的恢复。
- 会议录音转写进入 PostgreSQL 持久化队列，由独立异步 Worker 执行，支持并发抢占、
  超时、重试、取消、崩溃租约回收和结果恢复。
- 外部写操作统一经过权限、人工审核、幂等、敏感信息检查和审计。

## 本地开发

```powershell
conda activate office-multi-agent
python -m pip install -e ".[dev]"
uvicorn app.main:app --reload
```

默认运行确定性的旧版 StateGraph，适合无模型密钥的本地回归：

```env
ASSISTANT_RUNTIME=legacy
```

启用 Deep Agent：

```env
ASSISTANT_RUNTIME=deep_agent
AGENT_MODEL=提供商模型名称
```

模型密钥必须由部署环境或密钥管理系统注入，不得写入仓库。

## 容器化启动

复制 `.env.example` 为 `.env`，至少修改数据库密码和所需模型/MCP 配置：

```powershell
docker compose up --build -d
Invoke-RestMethod http://localhost:8000/ready
```

Compose 会启动：

- `postgres`：业务数据、LangGraph 检查点和长期存储；
- `app`：执行 Alembic 迁移后启动 FastAPI；
- `worker`：独立消费持久化异步任务。

停止服务使用 `docker compose down`。只有明确需要删除本地数据时才使用 `-v`。

## 异步长任务

创建会议转写任务：

```http
POST /meetings/{meeting_id}/transcriptions
X-Permission-Scopes: meeting:transcribe
```

查询和取消：

```http
GET  /tasks/{task_id}
POST /tasks/{task_id}/cancel
X-Permission-Scopes: task:cancel
```

Worker 可单独运行：

```powershell
python -m app.workers
```

关键参数：

```env
TASK_WORKER_POLL_SECONDS=1
TASK_WORKER_TIMEOUT_SECONDS=300
TASK_WORKER_LEASE_SECONDS=360
TASK_WORKER_RETRY_DELAY_SECONDS=10
```

租约时间应大于单任务超时。Worker 异常退出后，其他 Worker 会回收超过租约的任务。

## PostgreSQL 与恢复

```powershell
docker compose up -d postgres
alembic upgrade head
```

生产模式使用 `AsyncPostgresSaver` 保存 Agent/HITL 状态，使用
`AsyncPostgresStore` 保存跨线程长期数据。恢复时必须复用原 `thread_id`，身份仍从可信
运行上下文注入，不从检查点反序列化。

## Java RAG MCP

```env
KNOWLEDGE_MCP_URL=http://knowledge-mcp-adapter:8001/mcp
KNOWLEDGE_MCP_SERVICE_TOKEN=由密钥系统注入
```

主应用只调用 MCP 工具，不在 Python 项目中重复实现 RAG。生产模式缺少 MCP 地址或服务
令牌时会拒绝启动。

## 质量检查

```powershell
pytest
ruff check .
mypy app
docker compose config --quiet
```

设置 `TEST_DATABASE_URL` 后可运行 PostgreSQL 重启恢复测试：

```powershell
pytest tests/integration/test_postgres_deep_recovery.py -q
```

CI 包含 PostgreSQL 16 服务，会执行迁移并验证 HITL 跨进程恢复。

## 生产接入边界

仓库提供 Connector Protocol、Mock 和显式不可用实现，但不会伪装为已经接通真实企业系统。
上线前仍需接入真实报工、邮件、IM、ASR、Git、任务和目录 Connector，并配置认证网关、
对象存储、病毒扫描、DLP、TLS、备份恢复、指标追踪和告警。

详细改造说明见 [Deep Agent 改造说明](docs/DEEP_AGENT_MIGRATION.md)。
