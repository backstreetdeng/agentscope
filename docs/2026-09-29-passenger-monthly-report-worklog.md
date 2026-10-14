# 乘用车月报智能生成：2026-09-29 工作复盘

## 一、今天已经落地的业务能力

1. **月报能力升级**
   - 新能力统一使用 `skill_passenger_car_monthly_report`。
   - 旧版依赖人工整理 Excel 的月报能力已退出正式链路，不作为异常兜底。
   - 工作台选中的能力会作为请求参数传入后端；未选择月报能力时，不应触发月报专用连接检查与生成流程。

2. **后台长任务机制**
   - 前端提交后立即返回 `run_id`。
   - 后台按检查点执行，支持刷新后恢复、服务重启恢复、取消与继续、幂等归档。
   - 月报总任务不再受单次 360 秒调用限制；360 秒只作为单次底层调用的保护上限。

3. **确定的正式链路**

   ```text
   分批采集
       → 标准化月报数据包
       → 多源取证
       → 异常识别
       → 证据分级
       → 主旨句生成与校验
       → 携带 run_id 更新兼容模板
       → 输出并复核 PPT
   ```

4. **45 张卡片的数据门禁**
   - 映射表作为唯一卡片清单，执行时逐张核对。
   - 不再以“文本中出现数字”判断卡片可用；普通月度卡片必须包含当前报告月份，累计卡片必须覆盖当前报告年度。
   - “未更新”等字样仅作为卡片标题文本，不能代替对表格数据月份的判断。
   - 旧快照必须重新通过当前月份校验，不能因为历史上曾标记 45/45 就直接复用。

5. **主旨句增强链路**
   - 已提炼 3—8 月业务优秀报告的写法，保存为风格规则与示例索引。
   - 原始卡片 DOM、完整表格、优秀报告原文只在本地使用。
   - 当前选择的 MiniMax 或智谱模型只接收“逐页最小事实摘要”：本页主题、必要对比值、异常信号、事实编号和已分级的公开证据。
   - 政策、权益、新车、口碑和 Tavily 只接收公开检索词，不接收内部销量明细。
   - 模型结果返回后在本地反向校验数字和事实编号；无法追溯的数字、无 A/B 级证据的因果表达会被拒绝或降级为事实型表述。
   - 总览页最后生成，只允许引用已经校验通过的分页面结论。

6. **PPT 更新与交付**
   - “生成PPT版”必须携带本轮 `run_id`。
   - 后端只使用该 `run_id` 对应的数据包和主旨句包更新最新版兼容模板。
   - 写入后重新打开 PPT，核对目标页主旨句确实落入文件；重复点击同一任务不会生成重复归档。

## 二、今天发现并修复的关键问题

### 1. 360 秒不是根因

最初表现为 AgentScope 等待 Playwright MCP 工具返回 360 秒后超时。分层探针证明：

| 阶段 | 修复前结果 |
|---|---|
| `connect` | 正常，约 0.4—0.7 秒 |
| `list_tools` | 正常，约 0.02—0.6 秒 |
| `browser_tabs` | 触发浏览器初始化后无响应 |
| `browser_snapshot` / `browser_navigate` | 因浏览器未成功初始化而无法进入 |

因此故障属于“浏览器初始化问题”，不是 AgentScope 连接失败，也不是 stdio/npx 管道问题。

### 2. Playwright MCP 的 Windows 根因

当前环境：

- Windows
- AgentScope 2.0.3
- MCP Python SDK 1.27.2
- `@playwright/mcp` 0.0.82（项目固定版本；注册表最新为 0.0.83）
- Node.js 22.19.0
- Chrome 137.0.7151.120
- 当前配置没有 `--cdp-endpoint`

Playwright 调试日志显示两个连续问题：

1. 没有 `--no-sandbox` 时，Chrome GPU 子进程反复崩溃，浏览器主进程以访问冲突退出；Playwright MCP 0.0.82 没有及时把浏览器退出转换为工具错误，客户端只能等待到超时。
2. 加入 `--no-sandbox` 后，Playwright 1.64 的浏览器服务注册表需要写入 `%LOCALAPPDATA%/ms-playwright/b`，当前受控进程没有该目录的写权限，返回 `EPERM`。

修复方式：

- MCP 启动加入 `--no-sandbox`。
- 将 MCP 子进程的 `LOCALAPPDATA` 定向到项目 `runtime/playwright-mcp-localappdata`。
- 当前网络需要代理时，专用浏览器显式使用本机 `http://127.0.0.1:7897`；无该端口时自动回退为直连。
- 保持 `is_stateful=True`，Client 保存在连接器实例中，工具调用结束前不会销毁。
- 没有引入 CDP，不使用日常 Chrome 配置。

### 3. 修复后的最小复现结果

以下三条路径均完整通过：

```text
connect
→ list_tools
→ browser_tabs
→ browser_snapshot
→ browser_navigate("https://example.com")
→ browser_snapshot（识别到 Example Domain）
```

- AgentScope 2.0.3 + Streamable HTTP：通过。
- AgentScope 2.0.3 + stdio + 项目固定 Node CLI：通过。
- AgentScope 2.0.3 + stdio + Windows `npx.cmd` + 固定 0.0.82：通过。

结论：**不建议仅为本问题把正式环境从 stdio 改成 HTTP。** 两种传输在修复前都卡在浏览器初始化，修复后都正常。项目继续使用本地固定版本的 stdio 更简单；HTTP 可保留为独立进程部署或运维隔离时的备选。

## 三、保留的两层浏览器方案

1. **默认业务路径：本地只读 Playwright 驱动**
   - 使用月报专用持久 Chrome 配置。
   - 只开放固定数据源和受约束的数据读取操作。
   - 已验证代理接入后能访问数据源；当前专用配置停在登录页。

2. **可切换路径：AgentScope + Playwright MCP**
   - MCP 初始化故障已经修复。
   - 通过环境变量可切换验证，作为标准 MCP 接入能力保留。
   - 不复用用户日常 Chrome，也不依赖 CDP。

## 四、今晚未完成的业务动作

今晚未重新执行正式月报，是因为月报专用浏览器没有该同事账号的登录态；代理已经打通，但页面返回登录页。不能绕过登录，也不能复用旧数据冒充本轮采集结果。

## 五、下一次执行顺序

1. 在月报专用 Chrome 中由账号持有人完成登录，并进入月报数据源页面。
2. 执行一次连接检查，确认当前月份与 45/45 卡片均可用。
3. 在工作台选择“乘用车月报智能生成”，选择 MiniMax 或智谱并开始任务。
4. 观察 `run_id` 的真实阶段进度：采集、取证、证据分级、主旨句、PPT 更新。
5. 任务完成后点击“生成PPT版”，下载与该 `run_id` 绑定的文件。
6. 将生成版与业务优秀版逐页对照，重点评审：事实准确性、异常抓取、因果证据等级、主旨句信息密度和跨页重复。

## 六、主要改动文件

- `tools/monthly_report_browser.py`：数据源读取、月份新鲜度校验、直接驱动与 MCP 双路径、Windows MCP 修复。
- `scripts/probe_playwright_mcp.py`：分层、限时、可复现的 stdio/HTTP 诊断程序。
- `scripts/playwright_mcp_probe_config.json`：HTTP 对照测试配置。
- `utils/monthly_report_narrative.py`：逐页最小事实、公开取证、证据分级、主旨句生成与反向校验。
- `agents/market_strategy_agent.py`：无工具主旨句模型与约束提示。
- `app.py`：`run_id` 后台任务、检查点、恢复、结果和 PPT 更新。
- `assets/strategy-analysis.js`：前端任务恢复、阶段展示与 `run_id` 传递。
- `skills/market-analysis-skill/passenger-car-monthly-report/SKILL.md`：正式业务流程、数据最小化和质量门禁。

