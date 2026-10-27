# 研发代码图谱与变更验证

## 范围与定位

图谱项目名称为 `market-agent-web`，源码根目录固定为 `E:/AI/data/envs/helloagent/myproject`。复用本机已安装的 codebase-memory-mcp，供 Codex 研发查询使用；不向市场分析、用户洞察、月报、周报等业务 Agent 注册工具，不依赖它处理生产请求。

索引保留应用、前端、Agent、工具、集成层、Skill 可执行源码、测试、脚本、部署源码和研发文档。`.cbmignore` 排除运行目录、浏览器资料、凭据、业务原件、历史输出、依赖、备份和演示模板。被排除文件的运行依赖仍需通过源码和任务输入契约核对；它们不会因未入图而不再影响程序。

索引只存在当前用户缓存。刷新使用 `persistence=false`，不提交二进制图谱快照，不修改全局 Git 安全目录设置。不同会话必须复用已安装的同一版本和缓存根，不为本项目另启不同版本的全局 daemon。

## 日常流程

1. **确定任务基线。** 查看 Git 状态，记录当前已有的已修改、已暂存及与本任务有关的未跟踪文件。保留其他工作的修改；不要把所有 dirty 文件视为本次任务的产物。
2. **确认图谱状态。** 列项目、查 `index_status`。非当前会话项目可能不被监听；源码变化后刷新指定项目。不要仅凭 `ready` 或索引时间判断所有文件均新鲜。
3. **改前理解影响。** 使用 `search_graph` 找准确符号，`trace_path` 查看相关上下游，必要时查询其他关系类型。对所有引用的证据路径批量执行 `check_index_coverage`，读取关键源码。分页未结束、部分解析、未知新鲜度和被排除的范围均不能支撑完整性结论。
4. **实施改动。** 保持现有业务、凭据和浏览器会话规则。按任务范围修改，不依据零调用者自动删除函数，也不依据图谱推断已执行的线上行为。
5. **改后检查与验证。** 核对 Git 工作区和暂存区差异及新增文件；使用显式基线的 `detect_changes` 查看可能受影响符号，再按行为运行必要的单元/集成/页面检查。新增文件、动态注册、跨进程/网络关系需人工补充，不能只看 graph diff。
6. **交付证据。** 说明改了什么、运行了哪些验证及结果、哪些旧问题仍存在、有哪些未验证项。必要时刷新图谱，使后续任务读取的是改后的结构；重要架构决定同时写入仓库文档。

## 命令

从项目目录使用 PowerShell 7（`pwsh`）：

```powershell
# 状态；首次建立或源码变动后刷新
./scripts/codebase_memory.ps1
./scripts/codebase_memory.ps1 -Tool index_repository

# 概览和符号查询：name_pattern 使用 * 通配形式
./scripts/codebase_memory.ps1 -Tool get_architecture
./scripts/codebase_memory.ps1 -Tool search_graph -ArgumentsJson '{"name_pattern":"*build_market_strategy_agent*"}'

# 从符号查询结果复制准确 qualified_name，不靠猜测
./scripts/codebase_memory.ps1 -Tool trace_path -ArgumentsJson '{"function_name":"market-agent-web.agents.market_strategy_agent.build_market_strategy_agent","direction":"both","depth":2}'

# 证据文件覆盖；有缺口时读对应源码
./scripts/codebase_memory.ps1 -Tool check_index_coverage -ArgumentsJson '{"paths":["agents/market_strategy_agent.py","tools/custom_tools.py"]}'

# 相对当前 HEAD 的工作区影响，不默认与 main/远端比较
./scripts/codebase_memory.ps1 -Tool detect_changes -ArgumentsJson '{"base_branch":"HEAD","scope":"impact","direction":"both","depth":2,"limit":20}'
```

包装器禁止切换项目、根目录和跨项目刷新，默认完整索引且不导出图谱。`-Json` 返回原始 MCP JSON envelope，供留存证据或自动处理。直接调用 MCP 时同样应使用 `project="market-agent-web"`；跨项目任务需另行明确范围。

`detect_changes` 的分页游标和未展示条目需要按任务需求继续读取。使用其他开发基线时显式替换 `base_branch`。检查输出是否确实包含预期文件；Git 差异与图谱影响不是相互替代的。

当前仓库遗留大量未跟踪产物。`detect_changes` 的 changed_files 仍可能列出这些文件，即使 `.cbmignore` 已将它们排除在图谱外。因此全工作区的数字不是“本次任务改动数量”，不能直接作为本次发布范围。先记录任务开始时的状态，再按本次文件列表核对；查询截断时保留游标，不宣称已遍历全部影响。

## 按实际改动选择验证

下列为已有测试入口，不要求每次都全部执行。执行前先检查测试是否包含真实网络、数据库、Office 或浏览器操作；优先选择与本次变化相关的离线测试，真实业务验收另行记录。

| 改动范围 | 验证入口举例 |
|---|---|
| Agent Reach 搜索适配器 | `tests/test_agent_reach_adapter.py`，必要时增加真实搜索/正文读取检查 |
| 预测解析、计算、任务与导出 | `tests/test_passenger_forecast.py`、`test_passenger_forecast_jobs.py`、`test_passenger_forecast_exports.py` |
| 月报浏览器或任务 | `tests/test_monthly_report_browser.py`、`test_monthly_report_jobs.py` 及受影响的月报专项测试；保留现有已登录浏览器 |
| 周报执行或研究预算 | `tests/test_weekly_report.py`、`test_weekly_research_budget.py` |
| 市场 MCP 或数据集成 | `tests/test_market_mcp_plugins.py` 及对应数据接口测试，区分 mock 与真实数据源 |
| 前端 HTML/JS | 对变更 JS 使用 `node --check`，再检查受影响页面交互；静态语法通过不代表页面功能通过 |
| 仅图谱规则、包装脚本与研发文档 | 脚本解析、固定根目录检查、刷新/查询/覆盖/差异工具的实际调用；不为此启动业务任务或重跑全部报告 |

例如从项目目录运行一个离线测试模块：

```powershell
../Scripts/python.exe -B -m unittest discover -s tests -p test_agent_reach_adapter.py -v
```

2026-10-16 的迁移验证记录包含旧测试断言、假 PPTX mock 和宏观诊断函数异常等已知问题，见上层 `outputs/migration-audit-20261015/恢复结果-20261016.md`。这只是历史基线，不能自动豁免当前任务的新失败，也不能当作现在所有测试的状态。

## 限制

调用图主要描述静态可能关系。HTTP handler 字符串分派、反射/插件注册、异步任务、前端事件和模板内脚本都可能需要源码补查。图谱索引也不代表远程 MCP、数据库、业务文件和报告导出的真实运行验收。索引覆盖无已记录缺口不等于代码和关系完整。

首次抽查发现同名误连：图谱将 `skills/agent_reach/adapter.py` 中 `extract_field` / `extract_tail` 的 `re.search` 误列为本模块业务 `search` 的调用者。遇到 `search`、`run` 等常见名称，必须读调用语句确认接收者和导入来源，不能把显示的所有边直接当作事实。另有首页 CSS/HTML、旧页面、Word 渲染脚本和演示模板的部分解析记录；处理这些文件时检查最新覆盖报告并读标记范围，不为消除告警而改业务代码或隐藏真实源码。
