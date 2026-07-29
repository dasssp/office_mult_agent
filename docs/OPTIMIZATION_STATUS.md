# 八项优化交付说明

更新时间：2026-07-28

## 已完成内容

1. **PostgreSQL 工作流恢复**
   - 生产模式使用 `AsyncPostgresSaver`，应用启动时自动初始化检查点表。
   - `RequestContext` 仅作为运行时上下文传入，不会序列化到检查点。
   - 已启用严格 LangGraph msgpack 模式。

2. **Java RAG MCP 知识库边界**
   - `McpKnowledgeConnector` 使用 LangChain `MultiServerMCPClient`，通过 Streamable
     HTTP 直接调用 Java RAG 的 `knowledge_answer_tool`。
   - SSO Token 仅保存在请求级上下文中并写入 MCP 传输头，不进入 Prompt、工具参数、
     Checkpoint、缓存或日志；知识权限由 Java RAG 统一判定。
   - Redis 结果缓存按租户与用户隔离；即使缓存命中也要求请求携带 SSO Token。

3. **租户与身份控制**
   - 可信运行时上下文与 LLM 可控输入分离。
   - 文件元数据、读取、分析、导出和删除均按租户隔离。

4. **共享安全服务**
   - 审批记录按租户隔离，数据库模式下由 PostgreSQL 持久化。
   - 报告与会议纪要的外部写入使用租户范围的幂等服务。
   - 可替换的敏感数据检测会在外部分享前识别明显的凭据、身份证号和手机号。

5. **持久化结构**
   - 迁移 `20260728_02` 新增幂等记录、确认记忆、后台任务和调度表。

6. **业务 Agent 安全链路**
   - 报告提交和会议纪要发送会执行权限、审批、敏感数据、幂等和审计检查。
   - 邮件润色和数据分析仍为草稿/只读能力，不会直接触发外部写入。

7. **运行能力基础**
   - 已提供确认后记忆、后台任务状态和五段式 Cron 调度服务。
   - HTTP 完成日志只记录请求标识、路由、状态和耗时，不记录请求正文。

8. **验证与交付**
   - 单元测试和集成测试覆盖租户隔离、审批单次消费、幂等、敏感数据、确认记忆、任务状态与调度。

## 部署配置

```env
DATABASE_URL=postgresql+asyncpg://office_app:password@postgres:5432/office_multi_agent
LANGGRAPH_STRICT_MSGPACK=true
KNOWLEDGE_MCP_URL=http://localhost:8000/mcp
KNOWLEDGE_MCP_ANSWER_TOOL=knowledge_answer_tool
```

启动 API 前执行迁移：

```bash
alembic upgrade head
```

## 尚需接入的生产能力

本仓库不会宣称已接通企业系统。生产部署仍需由企业提供并接入：认证网关与可信身份注入、
Java RAG MCP 的真实工具契约与 SSO 验证环境、对象存储与病毒扫描、真实的报告/邮件/IM/Git/
任务连接器、任务队列、调度执行器、DLP、密钥管理和可观测性后端。

当前的服务边界与 Mock 旨在支持后续接入，同时避免在 Agent 节点中直接处理凭据或发起 HTTP 请求。
