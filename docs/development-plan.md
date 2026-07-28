# Deep Agent 改造开发计划

更新时间：2026-07-28

## 1. 改造策略

采用渐进式双运行时方案，保留原有固定 StateGraph，通过环境变量切换 Deep Agent。
现有 Service、Repository、Connector、权限、审批、幂等和审计能力继续作为确定性
业务底座，避免把关键业务规则迁移到 Prompt。

## 2. 阶段与交付

### 阶段一：主运行时

- 增加 `deepagents` 依赖；
- 新建 `app/orchestration`；
- 使用 `create_deep_agent` 构建主 Agent；
- 接入 `BaseChatModel`、RequestContext 和 Checkpointer；
- 增加 `ASSISTANT_RUNTIME`、`AGENT_MODEL`；
- 使用适配器保持现有 Assistant API 契约。

### 阶段二：领域子 Agent

- 注册报告、会议、邮件、数据和知识五个领域子 Agent；
- 配置独立系统提示词、专属工具和结构化响应；
- 限制 `general-purpose` 子 Agent，不向其提供领域工具；
- 将外部访问统一下沉到 Connector。

### 阶段三：动态规划与复合任务

- 使用内置 `write_todos` 管理计划；
- 使用 `task` 工具进行子 Agent 委派；
- 主 Agent 根据子任务结果更新计划并有限重规划；
- 最终响应汇总任务、证据、产物和警告；
- 通过 Prompt 和运行预算限制无界循环。

### 阶段四：上下文与长期记忆

- 使用 `StateBackend` 保存线程级工作区；
- 使用 Deep Agents 自动摘要和大结果卸载；
- PostgreSQL 模式接入 `AsyncPostgresStore`；
- 将确认记忆同步为租户、用户命名空间下的只读文件；
- 禁止 Agent 直接修改 `/memories` 和 `/policies`。

### 阶段五：审核恢复与长任务

- 报告审核、报告提交、纪要审核和纪要发送配置工具级 HITL；
- 将 Deep Agents 审核决策转换到现有恢复 API；
- 根据待执行工具计算最小权限范围；
- 将会议 ASR 拆分为启动和查询工具；
- 使用现有 BackgroundTaskService 持久化进度和失败码。

### 阶段六：验证与灰度

- 增加 Agent 架构、工具隔离、权限映射和记忆隔离测试；
- 保留原有测试作为回归基线；
- 本地默认使用 `legacy`；
- 开发租户先启用 `deep_agent`；
- 只读任务稳定后再启用写操作；
- 根据任务完成率、工具失败率、审核拒绝率和调用成本决定全量切换。

## 3. 灰度运行

旧运行时：

```env
ASSISTANT_RUNTIME=legacy
```

Deep Agent：

```env
ASSISTANT_RUNTIME=deep_agent
AGENT_MODEL=供应商:模型名称
```

模型供应商密钥由部署环境或密钥管理系统注入，不写入仓库。

## 4. 生产接入清单

代码已经提供边界但仍需企业环境提供：

- 真实报工、邮件、IM、ASR、Git、任务和目录 Connector；
- Java RAG 的正式 REST 契约和服务身份；
- 认证网关注入的可信 RequestContext；
- 对象存储、病毒扫描、DLP 和数据保留策略；
- 独立数据执行沙箱；
- Worker/队列和任务取消机制；
- PostgreSQL 备份恢复、TLS 和密钥管理；
- 指标、追踪和告警平台。

未提供以上接口时，生产模式必须显式失败，不得回退到 Mock 写操作。
