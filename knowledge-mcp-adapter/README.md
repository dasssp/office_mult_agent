# 企业知识库 MCP 适配层

这是一个独立的 Python MCP 服务，用于将只读知识查询转发到现有 Java RAG REST API。该服务不实现检索、向量化、重排或索引。

## MCP 工具

- `knowledge_answer_tool(query)`
- `knowledge_search_tool(query)`
- `knowledge_document_chunk_tool(document_id, chunk_id)`
- `knowledge_document_metadata_tool(document_id)`

工具参数不会暴露租户或员工身份。可信主应用通过 MCP 请求元数据注入租户、员工和服务间凭据，适配层校验后再将身份传递给 Java RAG。

生产环境配置：

```env
APP_ENV=production
JAVA_RAG_BASE_URL=https://java-rag.internal.example
MCP_SERVICE_TOKEN=请替换为服务间密钥
```

生产模式缺少 Java RAG 地址或服务间密钥时会拒绝启动。Java RAG 的端点路径、返回 Schema、认证请求头、错误码和超时策略仍需由企业知识库团队确认。

本地 Mock 开发：

```powershell
python -m pip install -e ".[dev]"
python -m knowledge_mcp_adapter.mcp_server
```

未配置 `JAVA_RAG_BASE_URL` 的开发环境使用明确标注的 Mock Java RAG。
