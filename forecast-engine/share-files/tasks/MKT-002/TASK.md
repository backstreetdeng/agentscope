# MKT-002 · 深度调研能力（deep-research Skill）

- 任务归属：市场板块；执行：TRAE（2026-11-06 用户确认立项，编号合法化）。
- 代码落点：`skills/deep-research/`、`agents/deep_research_agent.py`、`utils/deep_research_engine.py`、`utils/research_report_validation.py`、`app.py`（`run_deep_research_skill`）、`legacy_workbench.html`（智能体入口）、`home.html`（技能页卡片）。
- 方法论来源：deep-research-assistant research-guide，按汽车行业数据边界本地化。

## 范围

- 新建完整 Skill 包（SKILL.md / manifest / references 对比分析+研究报告两模板 / 产物契约 / validate_report.py 独立验收器）。
- 确定性编排引擎：模型仅 2 次受限单轮调用（检索计划 JSON + 报告正文）；搜索（主搜 any_search HTTP 直连 → 备搜 tavily）、精读、URL 去重、P0-P3 来源分级、虚构引用清理、参考来源清单生成全部由代码执行。
- 接入现有 skill runtime：run_id 隔离工作区 / 任务图 / 检查点 / 独立验收（skill-integration-standard）。
- 前端：技能页「深度调研」卡片 + 工作区智能体列表/tab/快捷问题/agent-card/URL ?agent= 直达。

## 已交付与验收（2026-11-06）

- 端到端（确定性编排）：run `skill-20261106-190501-8f4307b4` 78s / `skill-20261106-222847-e72c7b5e` 103s（双源），validation passed，报告发布至 `outputs/research/`。
- 单测：`tests/test_deep_research_validator.py`（6）+ `tests/test_deep_research_engine.py`（6），12/12 通过。
- 附带修复：`skills/anysearch/adapter.py` 支持 HTTP 直连（此前失败根因是本机缺 CLI 而非 key 失效）；用户提供的 key 已验证并写入 `.env`。

## 遗留项

- L01 口碑 MCP（reputation_*）未接入确定性取证引擎，现为 any_search + tavily 双源搜索 + 精读两源；口碑作为独立第三源待后续增强。
- L02 ~~浏览器端全链路点击实测~~ → 已完成（2026-11-09）：技能页卡片、#analysis 卡片、面板展开、示例填充、API 端到端 82s passed。
- L03 skill-integration-standard 12 项中跨 AI 复核项（Codex 侧能力对等检查）未执行。
- L04 146 数据库当晚连接超时导致 quant/口碑 MCP 间歇 502，属环境问题，146 恢复后自愈（与本任务代码无关）。

## 入口位置修正（2026-11-09，用户指出）

- 初版误把入口放进 `legacy_workbench.html`（废弃页，此前访谈证据问答已从中迁出，属重复迁移错误）；已按用户指示全部撤除，入口重做到新平台：
  - `home.html` #analysis（市场分析·技能工作台）新增第三张技能卡「深度调研」（MKT-002 标识）+ 页内原生工作台面板（示例问题 / 输入框 / 运行 / Markdown 报告渲染 / 报告下载链接）；
  - `home.js` 新增 DeepResearch 模块（/api/chat agent=deep_research，验收状态透出）；
  - 技能页深度调研卡片链接改为 `#analysis`（data-view-trigger）；
  - `legacy_workbench.html` 恢复原状（deep_research 残留 0）。
- 验证：面板展开/示例填充/输入框/按钮/状态实测通过；API 端到端 82s validation passed（run `skill-20261109-153541-e34fdea9`）；legacy_workbench 与 home.html 无 deep_research→legacy 残留链接。

## 内测修正（2026-11-09，用户报告点【开始调研】无反应）

- 根因排查：用户浏览器加载了旧版 home.js（资源版本参数 v=20261102e 长期未变，触发浏览器启发式缓存；此前 no-store 头已存在但用户页面未刷新）。
- 修复：① home.html 资源版本参数更新为 v=20261109；② home.js `setBusy(false)` 不再把运行状态覆盖回"待命"（内测真实运行时抓到的第二个 bug：完成态文案被 finally 覆盖）；③ 运行状态文案改业务语言。
- 内测证据：真实运行链路 PASS（展开→chip 填充→运行→报告 Markdown 渲染→下载链接 /outputs/research/）；API 端到端 82s passed（run `skill-20261109-153541-e34fdea9`）；JS node --check 通过。代理浏览器自身缓存污染导致其误报"连接拒绝/旧版本"，已用本地直连复核排除。
- 用户侧注意：浏览器需强制刷新一次（Ctrl+F5）加载 v=20261109 资源。
