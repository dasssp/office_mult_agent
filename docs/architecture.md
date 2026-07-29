# 系统架构说明

更新时间：2026-07-28

## 当前架构

项目使用单一 Deep Agent 编排运行时：主 Supervisor 动态规划，并通过 `task` 委派专业
Worker。开发环境缺少模型配置时不会构造 Assistant Runtime，也不会静默切换到另一套逻辑。

Deep Agent 运行时由以下层次组成：

```text
主 Agent
├─ TODO 规划、并行委派、失败检测、动态重规划、结果汇总
├─ Report CompiledSubAgent（生成 → 审核中断 → 提交中断）
├─ Meeting CompiledSubAgent（转写入队 / 生成 → 审核中断 → 发送中断）
├─ Email SubAgent
├─ Data SubAgent
├─ Knowledge SubAgent → Java RAG MCP
└─ General-purpose SubAgent（无领域工具）
```

Report 和 Meeting 不是一组平铺工具，而是独立编译的 LangGraph 子图。子图继承父图运行时
上下文和检查点，核心写操作仍由确定性的 Service、Repository 和 Connector 完成。

## Java RAG MCP 调用链

```text
浏览器 / SSO 网关
  └─ Authorization: Bearer <用户 Token>
      └─ RuntimeSecurityMiddleware（请求级 ContextVar，结束后立即清除）
          └─ Knowledge SubAgent
              └─ KnowledgeService（缓存前认证 + 引用结构校验）
                  └─ Redis 用户隔离缓存
                      └─ MultiServerMCPClient（streamable_http）
                          └─ http://localhost:8000/mcp
                              └─ Java RAG（鉴权、文档权限、检索与回答）
```

Token 不属于 Agent 状态，不允许模型生成，也不会进入工具参数、Checkpoint、缓存键或日志。
Python 侧只验证 Java RAG 返回的答案与引用结构，不重复实现文档权限规则。缓存键包含租户、
操作人、员工、角色和权限范围；缓存命中前仍要求当前请求存在 SSO Token。

## 动态规划与重规划

- 复杂请求先使用内置 `write_todos` 生成计划。
- 无依赖任务可在同一模型轮次并行调用多个 `task`。
- 中间件检查子任务 ToolMessage；发现 `failed`、`blocked`、`timeout` 或错误码后，会临时
  移除继续委派能力，要求先调用 `write_todos`。
- 重规划必须保留已完成项、标记失败项，并增加替代步骤或终止条件。
- `AGENT_MAX_DELEGATIONS`、`AGENT_MAX_PLAN_UPDATES`、递归上限和运行超时共同防止无限循环。

规划质量仍取决于所选模型，但“失败后不可直接继续委派”和总预算由代码强制执行。

## 上下文压缩与长期记忆

- `StateBackend` 保存线程级工作区，Deep Agents 自动摘要长对话并卸载大型结果。
- PostgreSQL 模式使用 `AsyncPostgresStore`。
- 用户明确确认的长期记忆同步到：

```text
("office-multi-agent", tenant_id, operator_id)
└─ /memories/confirmed.md
```

该路径对 Agent 只读，不能通过模型工具直接修改。

## 审核与跨进程恢复

Report 和 Meeting 子图直接使用 LangGraph `interrupt`，审核决策通过现有恢复 API 转换成
Deep Agents/LangGraph 决策格式。生产模式使用 `AsyncPostgresSaver`：

1. 子图在外部写操作前中断；
2. 检查点写入 PostgreSQL；
3. API 进程可以完全退出；
4. 新进程使用相同 `thread_id` 和可信 `RequestContext` 恢复；
5. 权限校验、幂等写入和审计继续执行。

`tests/integration/test_postgres_deep_recovery.py` 专门验证上述重启链路，CI 使用 PostgreSQL 16
执行该测试。

## 真正的异步长任务

会议转写不再在 HTTP 请求或 Agent 工具调用内部轮询。API/子图只向 `background_tasks`
表写入任务，独立 `python -m app.workers` 进程消费任务。

队列保证：

- `FOR UPDATE SKIP LOCKED` 支持多 Worker 安全抢占；
- 任务载荷、结果、进度、尝试次数和错误码持久化；
- 指数外部策略可通过重试延迟配置扩展，当前采用固定延迟；
- 支持排队态取消和运行态协作取消；
- Worker 崩溃后，通过租约超时回收 `running` 任务；
- 失败详情不写入数据库，只保存稳定错误码，避免泄露敏感正文。

## 尚需企业环境提供

代码已经完成框架和可测试边界，但下列内容不能由仓库伪造：

- 真实报工、邮件、IM、ASR、Git、任务和组织目录 Connector；
- 认证网关注入可信 `RequestContext`；
- 生产级对象存储、病毒扫描、DLP 和数据保留策略；
- PostgreSQL 高可用、备份演练、TLS、密钥管理、指标和告警；
- 所选模型在真实业务数据上的质量、成本和灰度评估。
