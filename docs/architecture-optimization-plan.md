# CATARC 工程实践对照与 HelloAgent 架构优化方案

> 依据：`reference_project/CATARC_Codex_Architecture_Guide_v1.1.md`
> 方法：指导书第 0 章要求"结论必须对应真实文件和代码，找不到证据时标记待确认"
> 分析日期：2026-10-23 · 本轮只读，未修改任何代码

---

## 0. 摘要

**指导书的核心贡献不是 CATARC 的业务代码，而是三条工程判据：**

1. **Harness 是横向保障体系，不是调用链上的一个节点** —— 状态、契约、门禁、预算、Checkpoint、Trace、验收包裹整个执行过程。
2. **固定控制面，动态决策面** —— 权限/状态/预算/门禁/审计由确定性程序强制；研究路径/工具选择/分析深度由 Agent 动态决定。
3. **模型散文永远不是证据** —— 结论必须能回溯到真实工具事件、来源、口径和版本。

**核实结论：HelloAgent 在这三条上的完成度远高于指导书第 5 章的预设。** 指导书怀疑"Skill 按钮可能只是填入预设文字"、"MCP 可能是 UI 占位"——**代码证据表明这两项怀疑已过时，不应据此"修复"**。

真实差距集中在 5 处，其中 2 处为 P0：

| 级别 | 问题 | 一句话 |
|---|---|---|
| **P0** | 凭据预检缺失 | 百炼 Key 实测 401，但 provider 仍为启用态、前端仍可选 |
| **P0** | 全局工具事件 + 串行锁 | `TOOL_CALL_EVENTS` 是模块级 list，审计正确性单点依赖 `AGENT_RUN_LOCK` |
| **P1** | trace_id 不贯穿任务 | 仅存在于 MCP 单次响应，无法关联阶段+工具+证据 |
| **P1** | 通用分析路径无控制面 | 最高频的 `/api/chat` 是纯 ReAct，无门禁、无证据收据 |
| **P1** | 无机器可读协议 | 阶段/状态/预算散落在 Python 常量与前端 JS 两处 |

CATARC 第 15 章 20 个测试场景映射结果：**13 项已满足 / 5 项部分满足 / 2 项不满足**。

---

## 1. 指导书解读：CATARC 真正可迁移的是什么

### 1.1 六层职责与"Harness 横向"

指导书 V1.1 花大量篇幅纠正一个常见误读：不要把架构画成
`Agent → Workflow → Skill → Harness → MCP` 的串行链。正确理解是：

| 层 | 职责 | HelloAgent 对应物 |
|---|---|---|
| Orchestrator / 意图路由 | 理解意图、选择流程 | `resolve_analysis_type()` + 前端 `agent_key` 显式选择 |
| Workflow Runtime | 阶段、依赖、分支、循环、调度专业 Agent | 4 套 Job Manager（monthly/macro/weekly/forecast） |
| 专业 Agent | 动态推理、选工具、返回结果与下一步建议 | `market_strategy_agent` / `user_insight_agent` |
| Skill | 专业方法契约，可被 Agent 选用或 Workflow 定点调用 | `market_analysis_skill` / `auto-weekly-report` / `html-ppt-skill` |
| MCP / Tool / API | 真实能力执行与受控数据访问 | 4 个 MCP Server + `api_server` + 7 个本地工具 |
| **Harness（横向）** | 状态、契约、Checkpoint、预算、门禁、Trace、Provenance、Verify | **分散存在，未统一**（见第 2.2 节） |
| Evidence Layer | 来源、口径、版本、证据 ID | `monthly_research_dag.py` 的 receipt 机制（仅月报路径） |

**关键点：** HelloAgent 的 Harness 能力**不是缺失，而是碎片化**——`skill_runtime/core.py`、`monthly_research_dag.py`、`quality_gate.py`、4 套 Job Manager 各自实现了一部分，缺少统一的 trace 和契约面把它们串起来。

指导书第 3.1 节明确说"Workflow 和 Harness 可以由同一批后端模块共同实现，不必强制拆成两个服务"——这正好适用于 HelloAgent 的现状：**不需要新建 harness/ 目录，需要的是把已有机制统一到一套上下文对象上。**

### 1.2 固定控制面 / 动态决策面

这是指导书最有价值的一条原则（第 4.2、7.2 节），也是判断"是否过度工程"的标尺：

- **固定控制面**（程序强制，不可协商）：权限、状态持久化、阶段契约、预算上限、硬门禁、审计留痕、恢复机制。
- **动态决策面**（Agent 自主，允许变化）：先查政策还是先查销量、是否补充检索、是否调用第二个 Agent、证据冲突后如何调整、哪些步骤不适用可跳过（但须记录原因）。

**反面警示（指导书第 4.2 节）：** "不能为了展示流程而强迫每个问题调用所有 Skill/MCP。"

HelloAgent 在这条上做得对：`eligible()` 函数（`utils/monthly_research_dag.py:40`）按工具名白名单筛选可用工具，Agent 提示词定义工具优先级但由 Agent 决定实际调用顺序。**这个设计应当保留，不要为了"架构完整"改成固定流水线。**

### 1.3 指导书中容易误读的三处（避免 Codex 走偏）

| 误读 | 指导书原文纠正 | 对 HelloAgent 的含义 |
|---|---|---|
| 把 `WORKFLOW.md` 当工作流引擎 | 第 3.3 节："文档本身不会自动执行流程" | 补文档不等于补能力；HelloAgent 的 Workflow Runtime 已存在于代码中 |
| 把 `HARNESS.md` 当 Harness 全部实现 | 第 3.3 节："真正的 Harness 是状态、协议、门禁…等跨阶段机制及代码" | 写 `docs/HARNESS.md` 只是第 5 步，不是第 1 步 |
| 为架构图好看引入新框架 | 第 16 节：拒绝"为了架构图好看而引入的微服务、消息队列、缓存或新 Agent 框架" | **禁止引入 LangGraph / Temporal / Airflow / Redis / FastAPI**，现有 ThreadingHTTPServer + AgentScope 足够 |

---

## 2. 现状核实：指导书的怀疑 vs 代码的证据

### 2.1 已被代码证伪的怀疑 —— 不要"修复"这些

指导书第 5 章基于 2026-07-05 的 `app_recovered.py` 提出怀疑。以下怀疑**已被当前代码证伪**：

| 指导书的怀疑 | 代码证据 | 结论 |
|---|---|---|
| "部分 Skill 按钮的行为是将预设任务文字填入输入框，这不等于已实现运行时 Skill 加载" | `skill_runtime/core.py` 提供 `SkillPackage`（含 `package_hash` 版本锁定）、`_safe_relative_path()` / `_inside()` 路径穿越防护、隔离运行工作区、持久化任务图；`mcp/skill_runtime_server.py` 暴露 18 个真实工具（`skill_activate` / `skill_plan_tasks` / `skill_run_script` / `skill_validate_run` 等） | **已是真实可执行包**，非 Prompt 注入 |
| "历史版本的 UI 文案曾将 MCP 标记为工程占位，必须核对当前 MCP 是否已真实接线" | 4 个 MCP Server 独立进程（policy:8811 / rights:8812 / new_car:8813 / reputation:8814），共 28 个工具，均带 `READ_ONLY_ANNOTATIONS` + Pydantic 输入校验；`integrations/market_mcp_plugins.py` 用 `asyncio.gather()` 并行发现，`HttpMCPConfig` + Bearer Token（`secrets.compare_digest` 防时序攻击） | **已真实接线**，且具备单插件失败隔离 |
| "是否有自动化测试" | `tests/` 下 **74 个测试文件**，含契约测试（`test_monthly_source_month_contract.py`）、UI 绑定测试（`test_web_skill_bindings.py`、`test_passenger_car_monthly_skill_ui.py`）、预算测试（`test_weekly_research_budget.py`）、Provider 可用性测试（`test_model_provider_availability.py`）、源复用测试（`test_macro_source_reuse.py`） | **测试基线已存在**（本轮未运行，实际通过率待确认） |
| "是否存在 Checkpoint、取消与恢复" | `utils/macro_report_jobs.py:79` `checkpoint(run_id, phase, data)` + `TERMINAL_STATUSES`（9 态）+ `recoverable` 标志；`utils/weekly_report_research.py:159` 按 sha256 复用已保存原文避免重复抓取；`app.py` `main()` 启动时 `recover_pending()` × 3 | **已实现**，且周报的 sha256 源复用正好满足 CATARC 4.6"重试避免重复扣费" |
| "UI 是否存在模拟进度或固定步骤" | `assets/strategy-analysis.js` 轮询真实 job 状态（`/api/*/jobs/{run_id}`），localStorage 存 active run_id；`assets/home.js` 的 `Plugins` 模块 60s 周期刷新、失败 5s 重试最多 2 次 | **未发现 `setTimeout` 伪造进度的证据** |

**给 Codex 的明确提示：** 指导书第 5 章是"审计线索"而非"现状判定"。上述 5 项已核实为真实实现，**不得以"补齐占位"为名重写这些模块**。

### 2.2 已被代码证实的差距

| # | 差距 | 代码证据 |
|---|---|---|
| **G1** | `trace_id` 不贯穿任务 | 全仓库 `trace_id` 仅 4 处，全在 `mcp/market_data/shared.py:124,134,141,167`，形如 `f"req-{uuid.uuid4().hex[:12]}"` —— **每次 MCP 响应随机生成**，与任务 run_id 无关联。一次月报运行横跨 4 个 MCP Server + Agent + Skill，无法用单一 trace 串联 |
| **G2** | 工具事件是模块级全局状态 | `tools/custom_tools.py:39` `TOOL_CALL_EVENTS: list[dict] = []`；`:50` `.clear()`；`:67` `.append(...)`。`app.py` 的 `AGENT_RUN_LOCK` 存在的**唯一理由**就是防止这个全局 list 串扰 |
| **G3** | 无机器可读协议文件 | `Glob myproject/**/*protocol*.json` → **0 结果**。阶段定义散落在：`app.py` 月报 6 阶段常量、`run_macro_monthly_skill()` 宏观 11 阶段、`macro_report_jobs.py:33` 状态枚举、`assets/strategy-analysis.js` 前端步骤标签 —— **四处独立维护** |
| **G4** | 通用分析路径无控制面 | `run_agent_once()`（`app.py:3239-3580`）对非 monthly/macro 的 `analysis_type` 直接进入 `agent.reply()` ReAct 循环（max_iters=6），返回 `{answer, agent, model_provider, tool_events, mcp_plugins, skill, skill_run}` —— **响应中无门禁结果、无证据收据**。`quality_gate` 是独立的手动 POST `/api/quality-gate` |
| **G5** | 无架构真源文档 | `docs/` 下 9 个文件（worklog / codebase-memory-workflow / directory-hygiene / 迁移记录 / 2 份 presentation / skill-integration-standard），**无 ARCHITECTURE.md、WORKFLOW.md、HARNESS.md** |
| **G6** | `app.py` 3800 行单体 | 混合 4 类职责：路由（`AgentDemoHandler`）、Job 编排（`MonthlyReportJobManager` 行 2608-3236 约 630 行）、Skill 执行（`run_macro_monthly_skill` 行 402-852）、持久化（`store_project_run` 行 1921）。**对比：macro/weekly/forecast 三个 Job Manager 已抽到 `utils/`，只有 monthly 仍在 app.py 内** |
| **G7** | 成本预算无统一面 | 已有：周报 `budget_seconds=180` + `max_iterations=8` + `search_budget=6`；月报 Skill `max_queries=4` + `max_items=6`；Agent `max_iters=6/8`；超时 180s/300s。**缺失：全仓库无 Token 计量、无费用估算、预算为各模块硬编码常量而非共享配置、通用路径预算触顶时不向 UI 返回原因** |
| **G8** | 用户洞察视图为静态 Demo | `home.html` 的 `insight` 视图是静态圈层画像；`build_user_insight_agent()` 后端完整可用，但除 `legacy_workbench.html` 外无现代 Web 入口 |

---

## 3. 逐项对照表（CATARC 第 4 章 12 条实践）

| CATARC 实践 | HelloAgent 现状 | 代码证据 | 差距 | 优先级 |
|---|---|---|---|---|
| **4.1** Agent 不是生产系统全部 | ✅ 已实现 | 4 套 Job Manager 后台执行，`recover_pending()` 启动恢复，状态落 `runtime/` | 无 | — |
| **4.2** 主流程明确 + 局部动态 | ✅ 长任务已实现<br>❌ 通用路径缺失 | 宏观 11 阶段确定性管道；`monthly_research_dag.eligible()` 工具白名单；Agent 自主选工具 | 通用 `/api/chat` 无任何阶段与门禁 | **P1** |
| **4.3** 先用确定性规则过滤，再调模型 | ✅ 月报/宏观已实现<br>❌ 通用路径缺失 | 月报 `data_gate` 阶段；`entity_present()` 正则校验实体确实出现在原文（**反幻觉硬门**）；`UNSUPPORTED_ATTRIBUTION_TERMS` 禁止把交叉表伪装成因果 | 通用路径模型直接产出结论，无前置数据校验 | **P1** |
| **4.4** 阶段输入输出有契约 | 🟡 部分 | `monthly_research_dag.py` 用 `jsonschema.validate`；`skill_runtime` 的 `artifact_template` + `skill_validate_run` | 契约内嵌在代码，未外化为可检查的协议文件 | **P1** |
| **4.5** 阶段状态显式持久化 | ✅ 已实现 | `macro_report_jobs.py:33` 9 态 `TERMINAL_STATUSES`；`checkpoints.jsonl` 追加日志；`data/project_runs.json` | 4 套 Job Manager 状态格式互不相同，无共享语义 | P2 |
| **4.6** Checkpoint / 取消 / 恢复 | ✅ 已实现 | `checkpoint(run_id, phase, data)`；cancel/resume 端点齐全；周报按 sha256 复用原文；`test_macro_source_reuse.py` | 无 | — |
| **4.7** 成本门禁是代码机制 | 🟡 部分 | 周报 `budget_seconds` / `max_iterations` / stagnant 检测；`max_iters`；超时 | **无 Token 计量、无费用估算、预算非集中配置、UI 不展示预算触顶原因** | P2 |
| **4.8** Provenance / 证据追溯 | 🟡 月报强，通用弱 | `monthly_research_dag.py` 文件头注释：**"Only the scheduler executes tools and assigns receipt IDs; model prose alone is never evidence"** —— 这是全项目最强的一条证据纪律 | receipt 机制仅服务月报；通用路径结论无 `evidence_id` 可回溯 | **P1** |
| **4.9** Verify 验证业务闭环 | ✅ 已实现 | 74 个测试文件；`ops/verify_market_api.py` 等 5 个 verify 脚本；`mcp/scripts/verify_deployment.py` | 无跨模块端到端冒烟（CATARC `verify_harness.py` 的等价物）；本轮未运行，通过率待确认 | P2 |
| **4.10** MCP 是受控入口 | ✅ 已实现 | Pydantic 校验 + `READ_ONLY_ANNOTATIONS` + Bearer Token（`secrets.compare_digest`）+ 分页限量 + `api_read_models.py` REPEATABLE READ + MD5 版本校验（409 VersionChanged） | 无 | — |
| **4.11** 真源与项目边界 | 🟡 部分 | `AGENTS.md`（规则）+ `README.md`（结构）+ `docs/skill-integration-standard.md` + `docs/directory-hygiene.md` 均完备 | **无架构真源文档**；新维护者须读 3800 行 app.py 才能理解链路 | P2 |
| **4.12** 可观测来自真实事件 | 🟡 部分 | `TOOL_CALL_EVENTS` 区分"模型声称调用"与"后端实际执行"；前端轮询真实 job 状态 | 事件仅存内存、每请求 `.clear()` → **不持久化、无法事后审计**；且为全局共享 | **P0** |

---

## 4. P0 / P1 / P2 问题清单

### P0 —— 阻断、数据污染、错误报告成功、凭据风险

**P0-1｜凭据预检缺失，失效 Provider 仍可选**

- 证据：`.env` 中 `DASHSCOPE_API_KEY` 实测调用百炼 `/v1/models` 与 `/v1/chat/completions` 均返回 **401**；但 `model_config/config.json` 中 `bailian_token_plan` 仍为启用态，前端下拉框仍列出"百炼 Qwen3.7 Plus"。
- 违反：`AGENTS.md`"Enable a provider only after a compatible API credential passes a real preflight request"；CATARC 第 15 章"凭据缺失/错误 → 返回安全、可操作的错误信息"。
- 业务风险：用户选中后需等到运行期（最长 180s 超时）才失败，且错误信息可能暴露端点细节。
- 备注：仓库已有 `tests/test_model_provider_availability.py`，**需确认它是否被接入运行期预检，抑或仅为离线测试**（待确认）。

**P0-2｜工具审计事件为全局可变状态，正确性单点依赖串行锁**

- 证据：`tools/custom_tools.py:39` 模块级 `TOOL_CALL_EVENTS`；`app.py` `AGENT_RUN_LOCK` 串行化所有通用 Agent 执行。
- 风险链：锁是**当前唯一**防止跨任务事件串扰的机制。一旦为提升并发而放宽锁，A 任务的工具调用会被计入 B 任务的 `tool_events` → **产生虚假审计证据并标记为成功** → 正是 CATARC 定义的 P0"错误报告成功"。
- 附带影响：通用 `/api/chat` 完全串行，两个用户同时分析即排队；事件不持久化，服务重启后无法复盘任一历史运行的真实工具调用。
- 违反：CATARC 第 15 章"并发请求 → 不发生共享状态串扰"；4.12"过程可观测必须来自真实执行事件"。

### P1 —— 真实工具审计、阶段契约、证据追溯、关键门禁

- **P1-1** `trace_id` 不贯穿任务（G1）：事故无法端到端复盘。
- **P1-2** 通用分析路径无控制面（G4）：最高频路径治理最弱，可产出无证据的战略结论且被标记成功。
- **P1-3** 无机器可读协议（G3）：阶段/状态/预算/前端标签四处独立维护，必然漂移。
- **P1-4** `app.py` 单体（G6）：每次改动的回归面覆盖全部 40+ 端点。

### P2 —— 断点续跑优化、成本、可扩展性、文档

- **P2-1** 成本预算无统一面、无 Token 计量（G7）。
- **P2-2** 缺架构真源三件套（G5）。
- **P2-3** 4 套 Job Manager 状态语义不统一（G5 关联）。
- **P2-4** 用户洞察视图静态 Demo（G8）。
- **P2-5** `legacy_workbench.html` 收尾（功能完整但入口已由 `initializeNewAnalysisLinks()` 移除，仍存在音频标签工作流等未迁移能力）。

---

## 5. 优化方案（6 个提案，均可独立分批实施）

> 共同约束：不引入新框架；不改现有 API 请求/响应契约（只允许新增字段）；不动前端整体布局；不重新划分 Agent/Workflow/Skill/MCP 职责。

### 提案 A｜`RunContext`：统一 trace 与事件作用域　**解决 P0-2 + P1-1**

**做法：** 新增一个显式贯穿调用链的上下文对象，用 `contextvars` 传递以避免改动 AgentScope 的 `ToolBase.call()` 签名。

```python
# 建议新增 harness/context.py（或并入 utils/）
@dataclass
class RunBudget:
    max_tool_calls: int
    max_model_iters: int
    max_seconds: int
    max_search_calls: int

@dataclass
class RunContext:
    run_id: str                 # 任务级，贯穿全流程
    trace_id: str               # 默认 = run_id
    task_type: str              # market_strategy|user_insight|monthly|macro|weekly|forecast|assistant
    stage: str
    budget: RunBudget
    events: list[dict]          # 实例级，取代全局 list
    started_at: str

CURRENT_RUN: ContextVar[RunContext | None] = ContextVar("current_run", default=None)
```

**改造点（最小侵入）：**

1. `tools/custom_tools.py`：`record_tool_call()` 改为写入 `CURRENT_RUN.get().events`；保留 `TOOL_CALL_EVENTS` 作为 fallback（无 context 时，如命令行 `main.py`），**保证现有 74 个测试不破**。
2. `app.py` `run_agent_once()`：入口处 `CURRENT_RUN.set(RunContext(...))`，退出时 reset。
3. 事件落盘：追加写 `runtime/runs/<run_id>/events.jsonl`，字段采用 CATARC 9.4 的 Tool Event Schema（`event_id` / `task_id` / `trace_id` / `event_type` / `tool_name` / `status` / `duration_ms` / `input_summary` / `output_summary` / `evidence_ids` / `error_code` / `timestamp`），**脱敏且限长**。
4. 4 套 Job Manager 在创建 job 时把 `run_id` 同时写为 `trace_id`，并在调用 MCP 时透传，使 `shared.py` 的响应级 `trace_id` 能挂靠到任务级 trace。

**收益：**
- 事件作用域从进程级降为任务级 → **可以安全放宽 `AGENT_RUN_LOCK`**（改为按 run_id 或直接移除只读路径的锁）。
- 事件持久化 → 满足 CATARC"服务重启后持久化任务状态不应无故消失"。
- 单一 trace 串联 Agent + 4 MCP + Skill → 事故可复盘。

**验证：** 新增并发测试（两个线程同时 `run_agent_once`，断言各自 `tool_events` 无交集）；重启后读取 `events.jsonl` 断言可还原。
**回退：** `contextvars` 未设置时自动回落全局 list，行为与今日一致。

---

### 提案 B｜`config/workflow_protocol.json`：外化阶段契约　**解决 P1-3**

**做法：** 单一机器可读文件，声明每种 `task_type` 的阶段、状态枚举与迁移、预算默认值、门禁 ID、产物契约。

**关键设计（防止 CATARC 第 3 章警告的"协议与代码长期不一致"）：**

- **代码仍是真源**，协议文件是代码的**声明镜像**。
- 新增一个测试 `tests/test_workflow_protocol_sync.py`：断言 Python 中的每个阶段常量（`macro_report_jobs.TERMINAL_STATUSES`、月报 6 阶段、宏观 11 阶段）都存在于协议中，反之亦然。**任一方向漂移即测试失败。**
- 新增只读端点 `GET /api/workflow-protocol`（**新增，不修改现有端点**），前端 `assets/strategy-analysis.js` 的步骤标签改为从此端点派生，消除前后端双份维护。

**推进范围：** 第一批只覆盖 **macro + monthly**（阶段已稳定）；weekly / forecast 待协议机制验证有效后再纳入。**不要一次性全量迁移。**

**收益：** 新增/调整阶段有单一改动点；前端步骤与后端阶段不可能漂移；CATARC 4.4 的"下游依赖哪些字段"可被程序检查。

---

### 提案 C｜通用分析路径的最小控制面　**解决 P1-2，业务价值最高**

**这是本方案中唯一直接提升分析结论可信度的提案。** 现状：通用 `/api/chat` 是纯 ReAct，可产出无任何确定性校验的战略结论并被标记成功。

**做法（严格遵循"固定控制面，动态决策面"，不把 ReAct 改成流水线）：**

1. **前置范围门禁（确定性，无模型）**
   复用已有解析规则，从 question 中抽取 `market / period / brands / vehicle_segments / powertrains`（字段名直接采用 CATARC 9.1 的 scope 结构）。
   - `period` 缺失或歧义 → 二选一：追问，或在响应 metadata 中**显式记录默认假设**（CATARC 第 10 章"请求/范围"门禁：规则检查；必要时追问或标注默认假设）。
   - 不允许模型静默假设时间范围。

2. **后置门禁自动化**
   把现有 `utils/quality_gate.py` 的 8 条规则（`source_authority` / `freshness` / `metric_consistency` / `scope_alignment` / `completeness` / `cross_validation` / `anomaly_conflict` / `traceability`）在 `run_agent_once()` 返回前**自动执行一次**，结果作为**新增字段** `quality_gate` 附加到响应。
   - 现有手动 `POST /api/quality-gate` **保持不变**（不改契约）。
   - 前端可选展示；不展示也不影响现有行为。

3. **证据收据复用**
   把 `monthly_research_dag.py` 已验证的 receipt 机制推广到通用路径的 Web/MCP 工具结果，使一条战略结论可引用 `ev_xxx`，而 `ev_xxx` 能解析回真实工具事件（URL / 数据周期 / 版本 / sha256）。
   - 保留该模块文件头已确立的纪律：**"model prose alone is never evidence"**。
   - 保留 `entity_present()` 这类反幻觉硬门（正则校验实体确实出现在原文）。

4. **保持动态**
   `max_iters`、工具选择顺序、是否补查、是否跳过某分析维度 —— **全部仍由 Agent 决定**。只增加控制面，不增加固定步骤。跳过须记录原因（CATARC 4.2）。

**明确不做：** 不为通用问答引入 Job/Checkpoint（CATARC 4.6"简单对话不需要完整 Job 机制"、3.2"简单问答无需一律启动长任务 Workflow"）。

**验证：** CATARC 第 15 章场景"结论无证据 → 关键结论被标记、降级或阻断"从 PARTIAL 转 PASS；"数据缺关键字段 → 不把缺失值伪装成 0"覆盖到通用路径。

---

### 提案 D｜`app.py` 渐进拆分　**解决 P1-4**

**不是重写，是按已有模式补齐一致性。** 关键观察：macro / weekly / forecast 三个 Job Manager **已经**在 `utils/` 下，只有 monthly 仍在 `app.py` 内 —— 拆分方向由项目自身既有约定决定，不是外部模板。

**分三批，每批独立可验证、可回退：**

| 批次 | 内容 | 行数 | 风险 |
|---|---|---|---|
| D1 | `MonthlyReportJobManager`（`app.py:2608-3236`）→ `utils/monthly_report_jobs.py` | ~630 | **最低**，与 `utils/macro_report_jobs.py` 完全同构 |
| D2 | `run_macro_monthly_skill()`（`app.py:402-852`）→ `utils/macro_report_pipeline.py` | ~450 | 低，纯函数迁移 |
| D3 | 路由分发：`AgentDemoHandler` 的 40+ 端点按域拆到 `web/routes/{intelligence,new_car,reputation,reports,jobs}.py`，Handler 通过 dispatch table 委派 | — | 中，**保留 ThreadingHTTPServer，不引入 Web 框架** |

**硬约束：**
- **零行为变更**。每批以"现有 74 个测试全绿 + `/api/config` 与一个样本 `/api/chat` 的响应字节级 diff 为空"为验收。
- D3 必须在 D1/D2 稳定后进行。
- 遵守 `AGENTS.md`：迁移前用 `codebase-memory` 的 `detect_changes` 核对调用路径，禁止新增本机绝对路径。

---

### 提案 E｜架构真源三件套　**解决 P2-2**

**放在最后做，不是第一步**（CATARC 3.3：文档不等于实现）。三份文件职责严格区分：

| 文件 | 内容 | 对应 CATARC |
|---|---|---|
| `docs/ARCHITECTURE.md` | 真实请求链路，标注实测文件名/函数名/端点名；未知处标"待确认" | 第 18 章成果 B |
| `docs/WORKFLOW.md` | **操作手册**：4 类长任务（monthly/macro/weekly/forecast）如何启动、查状态、停止、续跑、验收、排障；含月报浏览器会话保护规则 | 4.11 |
| `docs/HARNESS.md` | **运行时契约**：状态枚举与迁移、checkpoint 格式、门禁清单、预算默认值、provenance 规则、事件 Schema | 3.3 |

**约束：** 改了规则/接口/流程后同步更新对应真源；**不得每次会话新建重复的"过程总结"造成文档双轨**（CATARC 4.11 明令）。

---

### 提案 F｜用户洞察视图接入真实 Agent　**解决 P2-4**

**零后端改动、零 API 契约变更**，是最干净的增量：

- 后端 `build_user_insight_agent()` 已完整可用，`/api/chat` 已支持 `agent=user_insight_config`。
- 前端在 `assets/home.js` 新增 `InsightView` 模块，**复用 `ForecastView` 已验证的模式**（对话气泡 + Markdown 渲染 + 任务轮询 + 产物下载）。
- 替换 `home.html` `insight` 视图的静态圈层画像为真实交互区。
- **不改布局**：仍在既有 `data-view="insight"` 容器内，侧边栏导航与其余 9 个视图不受影响。

**附带收益：** 为 `user_insight_tagger` 工具（`tools/custom_tools.py`，规则+词典打标）提供真实 Web 入口，使 CATARC 8.2 的用户洞察证据链（匿名化 ID / 题号 / 原文片段 / `explicit`-`inferred` 类型 / 置信度 / 标签规范版本）具备落地载体。

---

## 6. 分阶段路线图

严格遵循指导书第 14 章"先审计，再分批改造"，**每阶段独立验收，未通过不进入下一阶段**。

| 阶段 | 内容 | 提案 | 交付物 | 验收命令/标准 | 回退 |
|---|---|---|---|---|---|
| **0** | 冻结基线 | — | Git 状态快照；运行全部 74 个测试并记录**真实通过率**与已知失败项 | `Scripts/python.exe -m unittest discover tests` | 无需（只读） |
| **1** | P0 修复 | A（部分）+ 凭据预检 | ① Provider 运行期预检，失败则 UI 禁用态 + 可操作错误信息；② `RunContext` 落地，事件按任务隔离并落盘 | 新增并发串扰测试通过；断开百炼 Key 后 UI 显示禁用而非运行期报错 | `contextvars` 未设时回落全局 list |
| **2** | 通用路径控制面 | C | 范围门禁 + 自动质量门禁 + 证据收据 | CATARC 场景 15「结论无证据」转 PASS；`/api/chat` 响应新增 `quality_gate` 字段且旧字段不变 | 门禁结果仅附加字段，前端不读即完全兼容 |
| **3** | 契约外化 | B | `config/workflow_protocol.json`（仅 macro+monthly）+ 同步测试 + `GET /api/workflow-protocol` | `test_workflow_protocol_sync.py` 通过；前端步骤标签改由协议派生 | 协议文件缺失时回落硬编码常量 |
| **4** | 结构治理 | D1 → D2 →（评估后）D3 | 拆分后的模块 + 零行为变更证明 | 74 测试全绿 + 样本响应字节级 diff 为空 | 每批独立 commit，可单独 revert |
| **5** | 可观测 + 真源 | E + F | 三份 docs + `InsightView` | 新同事仅凭 `WORKFLOW.md` 能独立完成一次月报续跑；洞察视图产出真实 Agent 结论 | 文档/前端增量，无回退风险 |

**每批完成后必须执行（指导书第 14 章阶段 5）：** 相关单元测试 → 集成测试 → 真实工具调用验证 → 证据链验证 → 错误路径与门禁验证 → 数据写入范围检查 → 密钥泄漏检查 → 与基线对比。
**只有实际运行并通过的检查才可标记通过；未运行的必须标记"未验证"。**

---

## 7. 验收：CATARC 第 15 章 20 个场景在 HelloAgent 的现状映射

| # | 场景 | 期望行为 | 现状 | 证据 |
|---|---|---|---|---|
| 1 | 普通简单问答 | 不启动无必要长工作流 | ✅ PASS | `/api/assistant/chat` 轻量路径，不加 `AGENT_RUN_LOCK` |
| 2 | 需要最新市场信息 | 实际调用检索并记录来源时间 | ✅ PASS | `TOOL_CALL_EVENTS` 记录真实执行；`monthly_research_dag` 分配 receipt ID |
| 3 | 只需内部知识 | 优先知识库，不大量 Web 搜索 | 🟡 PARTIAL | 提示词定义优先级，**无程序强制、无对应测试** |
| 4 | 工具未被调用 | UI 不能声称已执行 | ✅ PASS | `AGENTS.md`"Never claim completion from model prose alone"；`skill_validate_run` 为完成前置 |
| 5 | 工具返回空结果 | 记录空结果，补查/降级/阻断 | 🟡 PARTIAL | MCP 插件 fail-soft 为 `unavailable`；周报有 stagnant 检测；**通用路径待确认** |
| 6 | 工具超时/异常 | 有限重试，不无限循环 | ✅ PASS | 180s/300s 超时；周报 `max_iterations=8` + `budget_seconds=180`；预测"有限重试" |
| 7 | 证据相互矛盾 | 保留冲突，降低结论强度 | 🟡 PARTIAL | Skill 有 A/B/C 证据分级 + `UNSUPPORTED_ATTRIBUTION_TERMS`；`quality_gate` 有 `anomaly_conflict`；**通用路径未自动执行** |
| 8 | 数据缺关键字段 | 门禁，不把缺失伪装成 0 | ✅ PASS（月报） | `data_gate` 阶段；`test_monthly_source_month_contract.py` |
| 9 | 数据口径不一致 | 不直接合并统计 | ✅ PASS | `quality_gate.metric_consistency`；口碑跨源 `UNION ALL` 且显式区分来源，不做模糊竞品归因 |
| 10 | 预算/迭代超限 | 阻断或降级并显示原因 | 🟡 PARTIAL | 周报已实现；**通用路径仅 `max_iters`，触顶不向 UI 返回原因** |
| 11 | 页面刷新 | 持久化任务可恢复 | ✅ PASS | localStorage active run_id + `recover_pending()` + checkpoints |
| 12 | 长任务取消 | 安全边界停止并保存进度 | ✅ PASS | cancel 端点齐全；周报"任务停止，已有证据与检查点保留" |
| 13 | 长任务续跑 | 复用已完成单元，避免重复扣费 | ✅ PASS | 周报按 sha256 复用原文；`test_macro_source_reuse.py` |
| 14 | 输出缺必需字段 | Schema 验证失败，不标记成功 | ✅ PASS | `jsonschema.validate`；`skill_validate_run`；`presentation_validate` |
| 15 | 结论无证据 | 标记、降级或阻断 | 🟡 PARTIAL | 月报路径已实现（receipt + `entity_present`）；**通用路径未实现** → 提案 C |
| 16 | 报告导出失败 | 不报告成功，保留可诊断错误 | ✅ PASS | 预测"导出验收失败，有限重试"；宏观 `office_gate` / `layout_gate` |
| 17 | 服务重启 | 持久化状态不消失 | ✅ PASS | monthly/macro/weekly 均 `recover_pending()`；**forecast 待确认** |
| 18 | 凭据缺失/错误 | 安全、可操作的错误信息 | ❌ **FAIL** | 百炼 Key 实测 401，provider 仍启用且前端可选 → **P0-1** |
| 19 | 并发请求 | 无共享状态串扰 | ❌ **FAIL** | `TOOL_CALL_EVENTS` 全局 list；`AGENT_RUN_LOCK` 强制串行 → **P0-2** |
| 20 | UI 进度展示 | 与后端真实事件一致 | ✅ PASS | `strategy-analysis.js` 轮询真实 job 状态；未发现伪造进度证据 |

**统计：13 PASS / 5 PARTIAL / 2 FAIL。**
5 项 PARTIAL 中，4 项（场景 3/5/7/15）由**提案 C** 一并覆盖，1 项（场景 10）由**提案 A 的 budget 字段**覆盖。

---

## 8. TRAE / Codex 分工建议

2026-10-27 补充：本节保留为架构规划，不代表下列任务已分派或验收。当前实际任务及文件归属以 [共享任务清单](../forecast-engine/share-files/TASKS.md) 为准；协作遵循根目录 AGENTS.md 和 [共享目录说明](../forecast-engine/share-files/README.md)。首批仅启动 CHRONOS-001 成果交接，不据本节自动执行重构。

| 提案 | 主责 | 理由 |
|---|---|---|
| **A** RunContext + 并发隔离 | **Codex** | 触及 `tools/custom_tools.py` 与 `app.py` 核心执行路径，需并发测试与锁语义调整 |
| **B** workflow_protocol.json | **Codex** 主导，TRAE 消费 | 后端外化契约；TRAE 负责把 `strategy-analysis.js` 步骤标签改为从 `/api/workflow-protocol` 派生 |
| **C** 通用路径控制面 | **Codex** | 门禁逻辑、证据收据、`run_agent_once()` 改造 |
| **C-前端** 门禁结果与证据展示 | **TRAE** | 在既有结果面板内增量展示 `quality_gate` 与 `evidence_ids`，**不改布局** |
| **D** app.py 拆分 | **Codex** | 纯后端重构，需零行为变更证明 |
| **E** docs 三件套 | **TRAE** 起草 ARCHITECTURE/WORKFLOW，**Codex** 校核 HARNESS | TRAE 已完成全链路分析，可直接产出；Harness 运行时契约需 Codex 核对代码 |
| **F** 用户洞察视图 | **TRAE** | 零后端改动，复用 `ForecastView` 模式与现有 CSS 变量 |
| P0-1 凭据预检 | **Codex** | 涉及 provider 启用逻辑与 `/api/config` |

**协作纪律（沿用既有约束）：**
以现有代码为唯一基线 · 优先复用现有组件与 API · 每次修改前说明受影响文件与原因 · 影响布局或既有功能的改动先征得同意 · 修改后展示 Git Diff · 不自行提交/推送/部署。

---

## 9. 明确不做的事

依据指导书第 16 章"不要照搬 CATARC 的部分"：

1. **不引入新框架** —— 不加 LangGraph / Temporal / Airflow / Redis / FastAPI / 消息队列。现有 `ThreadingHTTPServer` + AgentScope 2.0.3 + PostgreSQL 足够，且 74 个测试建立在其上。
2. **不新建 `harness/` 空壳目录** —— 指导书 3.1 明确"Workflow 和 Harness 可由同一批后端模块共同实现"。HelloAgent 的 Harness 能力已分散存在于 `skill_runtime/`、`monthly_research_dag.py`、`quality_gate.py`、`utils/*_jobs.py`，**需要统一而非重建**。
3. **不重写已核实为真实的模块** —— Skill Runtime、4 个 MCP Server、4 套 Job Manager、Checkpoint/恢复机制、质量门禁规则集，均已实现且有测试覆盖。
4. **不复制 CATARC 的业务特化物** —— `trk2_*` 表名、Tavily/Firecrawl 主备策略、汽车新闻硬门、成刊状态、DOC 模板、特定端口与内网 IP、某日期的验收记录。
5. **不新增无独立价值的 Agent 角色** —— 不加 Planner / Reviewer / Critic / Memory。指导书 7.3 明确"不要为了体现多智能体而让每个请求都调用所有 Agent"。
6. **不把通用问答改成长任务流水线** —— 指导书 3.2 / 4.6：简单问答保持轻量同步返回。
7. **不移动大量文件以符合目录模板** —— 指导书第 13 章"不要为了符合目录模板而移动大量文件"，且 `AGENTS.md` + `docs/directory-hygiene.md` 已有本项目自己的落点纪律。
8. **不为架构美观牺牲动态性** —— 保留 Agent 自主决定研究路径、工具顺序、是否补查、是否跳过（须记录原因）的能力。

---

## 10. 最终判断标准

沿用指导书第 20 章，本次优化的成功**不以文件数量、架构图复杂度或 Agent 数量判断**，而以下列业务结果判断：

- [ ] 用户问题被正确理解并路由到合适能力
- [ ] Agent 根据实际证据动态决定下一步（**现状已满足，须保持**）
- [ ] 工具真实调用且结果被使用（**现状已满足，须保持**）
- [ ] 关键结论有可靠证据 —— **通用路径待补（提案 C）**
- [ ] 数据错误、缺失和冲突被识别 —— **月报已满足，通用路径待补**
- [ ] 长任务可观测、可停止、可恢复（**现状已满足，须保持**）
- [ ] Token、调用次数和执行时间受控 —— **待补 Token 计量（提案 A budget）**
- [ ] 错误可诊断 —— **待补 trace 贯穿（提案 A）**
- [ ] 结果可复核、可导出（**现状已满足**）
- [ ] 其他同事能通过文档和验证流程接手维护 —— **待补真源三件套（提案 E）**

**目标不是把 HelloAgent 变成 CATARC 的复制品，而是把它已经做对的证据纪律（`monthly_research_dag.py` 的 receipt 机制、`skill_runtime` 的完成门禁）从月报一条路径，扩展到通用分析这条最高频的路径上。**

---

*本文档为只读分析产物，未修改任何代码、未安装依赖、未启动服务。所有"待确认"项须在阶段 0 运行测试后核实。*
