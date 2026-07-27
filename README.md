# Office Multi-Agent

企业内部 Multi-Agent 办公助手。当前完成第一阶段的可运行基础工程：可信请求上下文、FastAPI、基础 LangGraph 路由、Mock Connector 和测试。

```powershell
conda activate office-multi-agent
python -m pip install -e ".[dev]"
uvicorn app.main:app --reload
pytest
```

开发环境会从请求头构造 Mock 身份；生产环境必须替换为已验证的认证提供方。
