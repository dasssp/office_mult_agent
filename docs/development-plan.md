# Deep Agent 改造开发计划

更新时间：2026-07-28

## 已完成阶段

### 第一阶段：主运行时

- 引入 Deep Agents，并保留 `legacy` / `deep_agent` 双运行时切换。
- 通过 `BaseChatModel` 注入模型，复用 FastAPI API 契约。
- 接入 LangGraph Checkpointer、递归上限和运行超时。

### 第二阶段：专业子 Agent

- 注册 Report、Meeting、Email、Data、Knowledge 和受限 General-purpose 子 Agent。
- Report、Meeting 改为真实 `CompiledSubAgent` 领域子图。
- 子 Agent 仅持有本领域工具，外部访问统一下沉到 Connector。

### 第三阶段：动态规划与复杂任务

- 使用 `write_todos` 维护计划，使用 `task` 委派子 Agent。
- 支持无依赖子任务并行委派。
- 检测失败、阻塞、超时和错误码，并强制先重规划再继续委派。
- 设置委派次数、计划更新次数、递归深度和总运行时间预算。

### 第四阶段：上下文和长期记忆

- 使用 `StateBackend` 管理线程工作区和大型中间结果。
- 使用 Deep Agents 自动摘要控制上下文长度。
- PostgreSQL 模式接入 `AsyncPostgresStore`。
- 确认记忆按租户和用户隔离，并禁止 Agent 直接写入记忆/策略目录。

### 第五阶段：审核、恢复和长任务

- 报告审核/提交、会议纪要审核/发送使用子图 `interrupt`。
- 使用 `AsyncPostgresSaver` 支持进程重启后的 HITL 恢复。
- 会议转写改为 PostgreSQL 持久化队列和独立异步 Worker。
- 支持多 Worker 抢占、超时、重试、取消、崩溃租约回收和结果查询。

### 第六阶段：验证和交付

- 单元测试覆盖子图结构、工具隔离、动态重规划和 Worker 状态机。
- SQLite 集成测试覆盖任务持久化与服务重建。
- PostgreSQL 16 CI 测试覆盖真实检查点中断和跨进程恢复。
- Redis 对 GitLab 活动、带引用知识问答和确认记忆实施隔离缓存与回源降级。
- GitLab Events API 通过独立 Connector 接入，CI 迁移到 `.gitlab-ci.yml`。
- 日报扩展为 GitLab、任务、邮件摘要和已审核会议纪要四路并行聚合，支持单来源故障降级。
- Docker Compose 同时交付 API、PostgreSQL、Redis 和 Worker。

## 灰度建议

1. 本地和 CI 默认保留 `legacy` 作为稳定回归基线。
2. 测试租户开启 `deep_agent`，先验证只读任务和复杂任务规划。
3. 再开放报告/会议写操作，观察任务完成率、重规划率、审核拒绝率、恢复成功率和成本。
4. 真实 Connector、认证网关、DLP、备份和告警全部到位后再生产全量切换。

## 企业接入待办

以下属于部署环境接入，不应在仓库内伪造完成：

- 真实报工、邮件、IM、ASR、任务和组织目录 Connector；
- 认证网关、密钥管理、TLS 和细粒度授权策略；
- 对象存储、病毒扫描、DLP、数据保留和删除策略；
- PostgreSQL 高可用、备份恢复演练、监控指标和告警平台；
- 模型效果、成本、延迟和安全红队评估。
