# AnySearch Skill Adapter

本目录是项目工程内的 AnySearch 能力适配层，避免业务工具直接依赖散落在用户目录里的外部 skill 路径。

## 当前职责

- 提供 `adapter.py`，封装 AnySearch CLI 调用。
- 从项目 `.env` 或系统环境读取 `ANYSEARCH_API_KEY`。
- 为 AgentScope 2.0.3 的 `ToolBase` 工具提供稳定调用入口。

## 路径策略

默认外部 CLI 路径：

```text
C:\Users\11489\.agents\skills\anysearch\scripts\anysearch_cli.py
```

如果未来外部 skill 移动，可以在 `.env` 中配置：

```env
ANYSEARCH_CLI_PATH=新的anysearch_cli.py绝对路径
```

业务代码只需要继续调用 `skills.anysearch.adapter.search()`。

## 工程结构关系

```text
tools/custom_tools.py
  -> skills/anysearch/adapter.py
  -> anysearch_cli.py
  -> https://api.anysearch.com/mcp
```

## 为什么不直接复制完整 AnySearch skill

完整 skill 包含跨平台 CLI、安装说明和上游维护文件。当前工程只需要稳定调用入口，
因此这里保留适配层而不是复制整套外部依赖。这样既能在工程里看见能力入口，
也避免后续上游更新时项目内出现多份难以判断的新旧脚本。

