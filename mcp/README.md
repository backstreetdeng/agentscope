# MCP 连接层说明

## 完整 Skill Runtime

`skill_runtime_server.py` 暴露网页智能体正在使用的同一套完整包运行时：Registry、
持久化 run、包内资源、任务图、工作区文件、预测、原生 PowerPoint 编辑与独立验收。

```powershell
.\scripts\start_skill_runtime_mcp.ps1
```

后台运行可使用 `-Background`。

默认 Streamable HTTP 地址为 `http://127.0.0.1:8820/mcp`。每个有状态工具显式接收
`run_id`，状态保存在 `runtime/skill-runs`，服务重启后仍可继续执行。

> 四大数据底座的最终 MCP Server 已落在 `market_data/`；服务器部署、数据库初始化和
> AgentScope 接入说明见 [FINAL_DEPLOYMENT.md](FINAL_DEPLOYMENT.md)。

当前 AgentScope 2.0.3 工程已经接入 Microsoft Playwright MCP，用于乘用车月报数据源的只读连接与预检。实现位于 `tools/monthly_report_browser.py`，Node 依赖锁定在项目根目录 `package.json`。业务默认保留本地只读 Playwright 驱动，设置 `MONTHLY_REPORT_BROWSER_BACKEND=mcp` 可切换到 MCP 路径。

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

浏览器原始工具不直接暴露给 Agent。`tools/` 中的 ToolBase 仅提供连接状态和按映射卡片读取能力，以保留工具审计、权限控制、异常兜底和 AgentScope 2.0.3 兼容性。

## 乘用车月报连接方式

- MCP 包：`@playwright/mcp`，项目本地安装。
- 传输：stdio，由 AgentScope 2.0.3 的 `MCPClient + StdioMCPConfig` 启动。
- 状态：`is_stateful=True`，Client 由连接器实例持有到工具调用全部结束。
- Windows 启动：使用 `--no-sandbox`，并把 MCP 子进程的 `LOCALAPPDATA` 定向到项目 `runtime/`，避免 Chrome GPU 初始化崩溃和 Playwright 浏览器注册表写入被拒绝。
- 代理：若本机 `127.0.0.1:7897` 正在监听，专用浏览器显式使用该代理；否则按直连启动。也可用 `MONTHLY_REPORT_BROWSER_PROXY` 覆盖。
- 浏览器：月报专用持久 Chrome 配置，不复用用户日常浏览器。
- 页面权限：固定月报数据源 URL；不向 Agent 开放任意导航、输入、保存、发布或脚本执行。
- 登录：第一次预检会打开专用 Chrome，用户完成登录后再次执行预检。
- 登录缓存：`runtime/monthly-report-browser-profile/`，已加入 `.gitignore`。

检查接口：

```text
GET /api/monthly-report-connector/status
POST /api/market-skill/validate
```

可选环境变量：

```text
MONTHLY_REPORT_SOURCE_URL=https://内部地址/page/...
MONTHLY_REPORT_BROWSER_HEADLESS=0
MONTHLY_REPORT_BROWSER_BACKEND=direct
MONTHLY_REPORT_BROWSER_PROXY=http://127.0.0.1:7897
```

首次登录必须保持 `MONTHLY_REPORT_BROWSER_HEADLESS=0`。完成登录并验证会话可持久化后，才可评估后台无界面运行。

## Playwright MCP 最小诊断

不要用增加超时掩盖浏览器初始化问题。使用项目探针逐层检查：

```powershell
E:\AI\data\envs\helloagent\Scripts\python.exe scripts\probe_playwright_mcp.py --transport stdio --stdio-launch node --timeout 40
```

正式判定必须依次通过 `connect`、`list_tools`、`browser_tabs`、`browser_navigate` 和 `browser_snapshot`。如需 HTTP 对照，单独启动 `@playwright/mcp --port 8931` 后使用 `--transport http --url http://localhost:8931/mcp`；当前 Windows 环境的故障曾在 stdio 与 HTTP 中同时复现，因此不能仅凭超时判断为 stdio 管道问题。
