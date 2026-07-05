# MCP 连接层占位说明

本目录用于后续接入 MCP Server，不在当前 AgentScope 2.0.3 Demo 中强行启用。

建议定位：

- `database/`：连接销量库、配置库、价格库、政策库。
- `file_store/`：连接企业文档库、访谈音频库、PPT/Excel/Word 文件库。
- `vector_store/`：连接用户原声、评论、访谈转写稿、行业报告向量库。
- `bi/`：连接 BI 看板、指标平台、销量/库存/线索仪表盘。
- `research_platform/`：连接调研项目、问卷、访谈样本、受访者画像。

推荐架构：

```text
AgentScope Agent
  -> tools/*.py 业务工具
  -> mcp/* MCP client/server adapter
  -> enterprise data systems
```

当前阶段不要让 Agent 直接依赖 MCP。建议先由 `tools/` 中的 ToolBase 包装 MCP 调用，
这样可以保留工具审计、权限控制、异常兜底和 AgentScope 2.0.3 稳定版兼容性。

