# Knowledge MCP adapter

This is an independent Python MCP service that forwards read-only knowledge requests to the existing Java RAG REST API. It does not implement retrieval, embedding, or indexing.

## Tools

- `knowledge_answer_tool(query)`
- `knowledge_search_tool(query)`
- `knowledge_document_chunk_tool(document_id, chunk_id)`
- `knowledge_document_metadata_tool(document_id)`

The tool schemas intentionally do not contain tenant or employee identifiers. Production deployment must replace `MockTrustedIdentityProvider` with a provider that reads a verified gateway request context. The included client is a contract adapter only: endpoint paths, response schemas, authentication headers, and error mapping must be confirmed with the Java RAG team before a live deployment.

For local Mock development, install with `pip install -e ".[dev]"` and run `python -m knowledge_mcp_adapter.mcp_server`. The server uses Streamable HTTP.
