# Deep Agent 改造说明

## 架构结果

当前项目支持两种运行时：

- `legacy`：原生 StateGraph 固定意图路由，适合无模型开发和确定性回归；
- `deep_agent`：一个主 Agent 动态规划并委派五个领域子 Agent。

Deep Agent 模式使用以下能力：

- `write_todos`：动态拆解和维护任务进度；
- `task`：把任务委派给隔离上下文中的子 Agent；
- `StateBackend`：线程级工作区和大结果卸载；
- 自动摘要：长对话接近上下文限制时压缩旧消息；
- `AsyncPostgresSaver`：线程状态、HITL 和故障恢复；
- `AsyncPostgresStore`：跨线程存储基础；
- 工具级 `interrupt_on`：外部写操作人工审核。

## 工具权限矩阵

| 子 Agent | 只读/草稿工具 | 写工具 | 审核权限 |
|---|---|---|---|
| report-agent | 工作事件查询、报告生成 | 审核、提交 | `report:review`、`report:submit` |
| meeting-agent | 会议信息、ASR、纪要生成 | 审核、发送 | `meeting:review`、`meeting:send` |
| email-agent | 邮件检查和润色 | 暂无发送工具 | 无 |
| data-agent | 行分析、文件分析、产物导出 | 仅租户产物写入 | 由文件服务控制 |
| knowledge-agent | Java RAG MCP 查询 | 无 | `knowledge:read` |
| general-purpose | 无领域工具 | 无 | 无 |

## 上下文边界

主 Agent 只保留任务计划、结构化结果、证据引用和产物引用。上传文件、转写和知识检索
明细停留在受控服务或子 Agent 上下文中。已确认记忆会同步到：

```text
("office-multi-agent", tenant_id, operator_id)
└── /memories/confirmed.md
```

该路径对 Agent 只读；新增或修改长期记忆仍必须调用现有确认记忆服务。

## 已知边界

- Deep Agent 模式需要真实可用的 LangChain ChatModel；
- 当前使用同步子 Agent；异步子 Agent 官方能力仍在快速演进；
- ASR 已提供非阻塞任务协议，但生产 Worker 和真实 ASR Connector 需要企业环境接入；
- 数据分析使用确定性工具，尚未开放模型生成代码的执行沙箱；
- 外部企业 Connector 在仓库中仍以 Protocol、Mock 或显式不可用实现交付。
