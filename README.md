# Office Multi-Agent 企业办公助手

基于 FastAPI、LangGraph、Deep Agents 和 PostgreSQL 构建的企业级多智能体办公助手。
系统支持日报/周报、会议纪要、邮件润色、文件分析与图表导出、企业知识问答，并通过
使用 LangChain MCP Client 通过 Streamable HTTP 直接连接 Java RAG 暴露的 MCP Server，并按请求安全透传
SSO Token；知识权限由 Java RAG 统一判定。

## 架构亮点

- 一个主 Agent 负责任务理解、TODO 规划、并行委派、动态重规划和结果汇总。
- Report、Meeting 使用真实的可编译 LangGraph 领域子图；Email、Data、Knowledge
  使用隔离工具集的专业子 Agent。
- 日报将 GitLab、任务系统、已发送邮件摘要和已审核会议纪要并行聚合为统一
  `WorkEvent`；单个来源失败时保留其他来源结果并返回明确警告。
- 子任务失败后强制先更新计划再继续委派，并限制委派次数、计划更新次数、递归深度和超时。
- Deep Agents 自动进行上下文摘要，大型中间产物卸载到工作区；确认后的长期记忆按
  `tenant_id + operator_id` 隔离保存。
- 报告审核/提交、会议纪要审核/发送通过 LangGraph `interrupt` 中断，使用 PostgreSQL
  Checkpointer 支持进程重启后的恢复。
- 会议录音转写进入 PostgreSQL 持久化队列，由独立异步 Worker 执行，支持并发抢占、
  超时、重试、取消、崩溃租约回收和结果恢复。
- Redis 对 GitLab 活动、带引用的知识问答和已确认长期记忆提供租户/权限隔离的短时缓存；
  缓存故障时自动回源，不影响核心流程。
- 外部写操作统一经过权限、人工审核、幂等、敏感信息检查和审计。

## 本地开发

```powershell
conda activate office-multi-agent
python -m pip install -e ".[dev]"
uvicorn app.main:app --reload
```

配置 Supervisor 使用的模型：

```env
AGENT_MODEL=提供商模型名称
```

模型密钥必须由部署环境或密钥管理系统注入，不得写入仓库。开发环境没有配置
`AGENT_MODEL` 时，领域 API 仍可运行，Assistant API 会明确返回 `503`；生产环境缺少模型
配置时拒绝启动。

## 代码结构

```text
app/
├─ orchestration/       # Supervisor、Worker 配置、领域子图与 Agent 工具
├─ domain/              # 确定性领域服务，不包含 LLM/ReAct 循环
├─ connectors/          # GitLab、邮件、MCP 等外部系统边界
├─ repositories/        # PostgreSQL 持久化
├─ services/            # 审核、审计、缓存、文件和异步任务等应用服务
└─ api/                 # FastAPI 路由与协议适配
```

实际 Agent 只存在于 `app/orchestration`；数据统计、报告、会议等确定性能力统一使用
`*Service` 命名，避免把普通业务类误认为自主 Agent。

## 容器化启动

复制 `.env.example` 为 `.env`，至少修改数据库密码和所需模型/MCP 配置：

```powershell
docker compose up --build -d
Invoke-RestMethod http://localhost:8000/ready
```

Compose 会启动：

- `postgres`：业务数据、LangGraph 检查点和长期存储；
- `redis`：只保存可重建的热点读数据，不承担事实数据持久化；
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
KNOWLEDGE_MCP_URL=http://localhost:8000/mcp
KNOWLEDGE_MCP_ANSWER_TOOL=knowledge_answer_tool
KNOWLEDGE_MCP_TIMEOUT_SECONDS=15
```

主应用只调用 MCP 工具，不在 Python 项目中重复实现 RAG。生产模式缺少 MCP 地址时会
拒绝启动；每次真实知识查询必须携带 `Authorization: Bearer <SSO Token>`。Token 只进入
Java RAG MCP 的 HTTP 请求头，不进入 Prompt、工具参数、Checkpoint、Redis 或日志。
如果主应用运行在 Docker 中、Java RAG 运行在宿主机，请将地址配置为
`http://host.docker.internal:8000/mcp`。

## Redis 缓存

```env
REDIS_URL=redis://localhost:6379/0
REDIS_DEFAULT_TTL_SECONDS=120
REDIS_KNOWLEDGE_TTL_SECONDS=120
REDIS_MEMORY_TTL_SECONDS=300
```

当前采用 Cache-Aside：

- GitLab 活动查询：按租户、员工和日期范围缓存；
- Java RAG MCP 成功响应：仅缓存带引用的结果，并纳入用户、角色和权限范围；
- 已确认长期记忆：读取时缓存，新增或更新后立即失效。

审批、提交、审计、LangGraph Checkpoint 和异步任务状态不缓存，继续以 PostgreSQL 为
事实来源。Redis 键只暴露命名空间和摘要，不直接包含租户、用户、查询正文等敏感值。

## GitLab 接入

```env
GITLAB_BASE_URL=https://gitlab.example.com
GITLAB_ACCESS_TOKEN=由密钥系统注入
GITLAB_REQUEST_TIMEOUT_SECONDS=10
```

日报采集通过 GitLab Events API 读取用户活动。生产模式缺少 GitLab 地址或访问令牌时
拒绝启动；令牌不会写入日志或缓存。仓库 CI 已迁移为根目录 `.gitlab-ci.yml`，包含
单元/静态检查、Redis 集成测试、PostgreSQL 恢复测试和镜像构建。

## 多数据源日报

日报与周报默认并行聚合以下只读数据：

- GitLab 推送、Commit 和合并请求活动；
- 当前员工的任务状态；
- 当前员工已发送邮件的主题和业务摘要，不读取原始完整正文；
- 当前员工创建且已经审核或发送的会议纪要及会议结论。

所有来源统一转换为带 `source_type`、`source_id` 和 `evidence_url` 的 `WorkEvent`。
格式无效或带敏感标记的邮件会被忽略；单个 Connector 不可用时，系统使用其他来源继续
生成草稿，并把缺失来源写入 `source_warnings`。生产环境仍需按照企业邮件系统的实际
接口实现 `EmailConnector.list_activity`。

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

设置 `TEST_REDIS_URL` 后可运行 Redis 集成测试：

```powershell
pytest tests/integration/test_redis_cache.py -q
```

GitLab CI 包含 Redis 7 和 PostgreSQL 16 服务，会验证缓存读写、数据库迁移以及 HITL
跨进程恢复。

## 生产接入边界

仓库提供 Connector Protocol、Mock 和显式不可用实现，但不会伪装为已经接通真实企业系统。
上线前仍需接入真实报工、邮件、IM、ASR、任务和目录 Connector，并配置认证网关、
对象存储、病毒扫描、DLP、TLS、备份恢复、指标追踪和告警。

详细设计见 [系统架构说明](docs/architecture.md)。
