# BCI-004：竞品洞察 · 用户洞察档案 tab

```
task_id: BCI-004
title: 竞品洞察 · 用户洞察档案 tab
stage: TESTED
owner: TRAE
commit_paths: competitor_insight/docs/archive-tab-design.md,competitor_insight/tasks/BCI-004,competitor_insight/tasks/tasks.md,competitor_insight/BOARD.md,competitor_insight/HANDOFF.md,competitor_insight/server,competitor_insight/web/bci-profile.js,competitor_insight/web/bci-profile.css,competitor_insight/tests,competitor_insight/templates,ops,outputs/competitor-insights/BCI-004
updated: 2026-11-07
blocked: no
next: 用户验收 7860 页面与 10 人试点数据后确认上线
evidence: outputs/competitor-insights/BCI-004/
```

## 1. 目标与边界

**目标**：交付「竞品洞察 → 洞察档案」tab 的技术实施方案，并把方案拆成可直接开发、可独立验收的步骤。业务口中的「① 用户洞察档案」= 当前页面 tab ②「洞察档案」（tab ① 已是数据源筛选）；技术标识统一用 `profile`。

**本方案要解决的问题**：一份档案 = 一个受访者 × 模板维度集合（当前两套 ready 模板均为 43 维）。要求：单人查看、多人合并导出、每条结论可回溯原话、模板驱动而非前端写死、真实 `.xlsx` 导出。

**本轮边界**：

- 进入开发后，先只新增 `competitor_insight/server/`、`web/bci-profile.*`、模板映射与测试；**在收到「入库完成」前不改共用文件、不启动 7860**。数据库在 D2/D7 建表后按方案写入 `bci.*`，其余查询只读。
- D6 之前不改 `home.html`、`home.css`、`home.js`、`app.py`、`web/bci.js`、`web/templates.json`；D6 起按方案 §1.1 的最小改动接线。
- 不自行扩展需求：不做车型矩阵、不做评分推荐、不做自由指令 Agent、不做多人并排查看。
- 不编数据：所有数据结论带三态与计数；文件推断与实测分开标注（`coverage.csv` 有 `evidence_basis` 列）。
- 已定决策：Q1 批准建 `bci` schema + 4 表；Q2 模型自动生成 + 只读；Q9 先 10 人试点；Q11 无来源维如实标注；Q12 评分只对有分数者生成。

**允许写入**：方案阶段已写 `competitor_insight/docs/`、`tasks/`、`BOARD.md`、`HANDOFF.md`、`outputs/competitor-insights/BCI-004/`；开发 D1–D5 仅新增 `competitor_insight/server/`、`competitor_insight/web/bci-profile.js`、`web/bci-profile.css`、`competitor_insight/templates/*.source-map.json`、`competitor_insight/tests/`、`ops/`（DDL 脚本）；D6 起才可改共用文件。

## 2. 验收标准（方案阶段）

| # | 验收项 | 判定方式 | 证据 |
|---|---|---|---|
| A1 | 整体架构清楚，三个 tab 边界明确 | 读方案 §1 | `archive-tab-design.md` |
| A2 | 数据模型可直接建表，含证据与模板升级策略 | 读 §2 的 DDL 与规则 | 同上 |
| A3 | 模板驱动机制含校验规则与 source-map | 读 §3 | 同上 |
| A4 | 接口清单齐全（路径/入参/出参/权限） | 读 §4 | 同上 |
| A5 | 前端结构、状态、性能、导出方案可执行 | 读 §5 | 同上 |
| A6 | 数据来源"有/无"分开，缺口有补数原则 | 读 §6 | 同上 |
| A7 | 任务拆分有依赖与可判定验收 | 读 §7 | 同上 |
| A8 | 开放问题可逐条拍板 | 读 §8.1 | 同上 |

## 3. 步骤与结果

| # | 步骤 | 状态 | 实际结果 | 证据 |
|---|---|---|---|---|
| S0 | 读规范、既有任务、模板、原型、现有前端与接口 | 完成 | 读 `RULES.md`、`README.md`、`BOARD.md`、`HANDOFF.md`、`BCI-001/002/003 TASK.md`、两套模板、`bci.js`/`bci.css`/`templates.json`、`home.html` 的 bci 视图、`app.py` 路由与 POST 白名单、访谈 Schema、原型第 218–262 行与模块① JS | 本任务 §5 |
| S1 | 写技术方案（架构/数据/模板/接口/前端/数据现状/拆分/风险） | 完成 | `competitor_insight/docs/archive-tab-design.md`，覆盖用户要求的 8 个部分 | 该文件 |
| S2 | 只读探查数据现状 | 完成（实测） | 已直连 `192.168.3.146:5432` 只读实测：63 人、85 题、85 标签、5355 答案、81437 证据、45244 标签证据；`interview` 无人口统计列；63 人无埃安车型；仅 3 人提及埃安 | `20261106-coverage/tag-inventory.log` |
| S3 | 建任务并同步三方 | 完成 | 本文件 + `tasks/tasks.md` + `BOARD.md` + `HANDOFF.md` | `check_board.py` |
| S4 | 43 维覆盖率盘点 | 完成 | 43 维逐维 SQL 实测：success 19 / partial 16 / failed 8；必填 38 维中 17/14/7；产出 `coverage.csv`（应查 63、实查 63、逐维命中）与 10 人试点名单 | `competitor_insight/docs/coverage.csv`、`20261106-coverage/coverage.log` |
| S4b | 题项映射 `source-map.json` | 转为 D1 | §6 已给每维来源与题号；Q11/Q12 拍板后并入开发第 1 步 | 计划产出 `competitor_insight/templates/user_insight_archive.source-map.json` |
| D0 | Q11/Q12 决议入档 + 开发步骤拆分 | 完成 | 方案 §0 D9/D10、§5.7、§6.4、§7.1、§8.1 Q4/Q11/Q12 已更新；本文件 §10 给出 D0–D8 顺序、依赖与验收；共用文件闸门已写明 | 方案 §7.1、本文 §10 |
| D1 | source-map 契约层 | 完成（2026-11-07） | 新增 `templates/user_insight_archive.source-map.json`（43 维）、`server/source_map.py`、`server/template_registry.py`、`tests/test_source_map.py`；fill_mode 分布 tag 22 / metadata 2 / derived 1 / llm 10 / none 8；8 个无来源维全部带 `no_source_reason` 且未声明任何来源；61 个题号与 56 个标签经真实库校验全部命中；单元测试 23/23 通过 | `outputs/competitor-insights/BCI-004/20261107-d1-sourcemap/validate.log` |
| D2 | 存储层 | 完成（2026-11-07） | `ops/bci_archive_ddl.sql` + `ops/bci_archive_ddl_owner.sql` + `ops/apply_bci_archive_ddl.py`；`bci` schema 与 4 表、约束、索引已在真实库创建；loader 实测 `has_schema_usage/create(bci)=True`；insert/select/delete 冒烟通过并清理；`server/db.py`、`server/archive_store.py`（PG + 文件后端）与 `tests/test_archive_store.py` 完成；全量测试 32/32 通过 | `outputs/competitor-insights/BCI-004/20261107-d2-ddl/apply.log` |
| D3 | 生成器 | 完成（2026-11-07） | `server/archive_generator.py` + `server/evidence_gate.py` + `tests/test_archive_generator.py`；确定性维（tag/metadata/derived）不调模型；LLM 维只回证据 ID，原话由服务端截取（超 300 字截断）；伪造 ID / 跨人证据 / 非法枚举 / 证据超 5 条 / 非 JSON 均整人失败；8 个无来源维落 `no_source_reason`；满意度只取 Q59 数字（区间取中点并保留原文），无分数落描述性或未给出；单测 24 项 + 全量 56/56 通过；真实库 R003/R001/R002 各生成 43 维（只读，不落库） | `outputs/competitor-insights/BCI-004/20261107-d3-generator/generate-probe.log` |
| D4 | 查询/运行/导出服务 | 完成（2026-11-07） | `server/archive_api.py`（模板/受访者/详情/生成/轮询/原话/导出，可直接调用，未挂路由）、`server/quote_service.py`（答案/证据/标签证据/档案值四类检索 + 按 ID 刷新原话）、`server/export_service.py`（openpyxl 真 xlsx 三 Sheet + 单人 md，内存 bytes）；`tests/test_archive_service.py` 25 项；无来源行导出为「本期无来源：原因」，评分缺失带 `score_source=missing`；真实库只读：63 人、43 维、12 组、R001 详情空态、找原话命中 | `outputs/competitor-insights/BCI-004/20261107-d4-api/probe.log` |
| D5 | 前端新模块 | 完成（2026-11-07） | `web/bci-profile.js`（约 920 行，`window.BciProfile`、`[data-bci-profile]` 自动初始化）、`web/bci-profile.css`；修复 `readScope` 层级（必须返回完整 `{version,datasources}`）与 rowspan 残留 `groupCell`；模块列按连续同组 rowspan 合并 | `outputs/competitor-insights/BCI-004/20261107-d5-frontend/check.log` |
| D6 | 共用文件接线 | 完成（2026-11-07） | `app.py` 新增 `/api/bci/archive/{template,respondents,detail,run,quote}` GET 与 `{generate,export}` POST（惰性单例 `ArchiveService`，独立线程，不占 `AGENT_RUN_LOCK`）；`home.html` 启用 tab ②、挂载 `[data-bci-profile]`、引入 `bci-profile.css/js`；`bci.js` 切到 tab ② 时才 `BciProfile.init`，面板未展开不预加载；临时端口探针 19/19（真实库只读：43 维/12 组/63 人/R001 空态/找原话命中；静态资源与首页接线 PASS） | `outputs/competitor-insights/BCI-004/20261107-d6-wiring/probe.log` |
| D7 | 10 人试点生成写库 | 完成（2026-11-07） | 真实 DeepSeek（`deepseek-v4-flash`，新增 `server/llm_client.py`）生成并写入 `bci.*`：10/10 成功、每人 43 维；19 个 success 维 183/190 命中（12 维满员，7 维 9/10），7 个缺口均落 `no_data_reason`；8 个无来源维全部标注「本期无来源」；LLM 值证据 ID 全部有效；R046 购车属性因「换购；增购」互斥标为 `suspect` 待复核；覆盖率 65.79%–76.32% | `outputs/competitor-insights/BCI-004/20261107-d7-pilot/pilot.log` |
| D7b | R046「购车属性」互斥值核实与修正 | 完成（2026-11-07） | 链路：`fill_mode=tag` ← 标签「首增换购属性」`TAG-377357cc173d61c8ce47`（原值「换购；增购。」，可信）。回到原话 `TEI-91315ed80cf5faca5d12`（3055.8–3089.4）与证据 `EV-978feb41abc39345abbd`：旧车本田雅阁购入当时仍由妻子开、没有卖掉，按模板题 1「已婚以小家庭（不含父母）为单位」应判**增购**，`interview.purchase_type=增购` 交叉一致。已改为 `value_text=增购`/`fill_mode=tag`/`review_status=ok`，原值、原原因、判断依据、证据 ID 与时间段保存在 `source_ref.correction`；覆盖率 68.42→71.05（27/38），状态仍 partial。全库仅此 1 条互斥；`R046` 与 `RE010` 非同一人，库中不存在 `RE010`（早前报告为笔误，实为 `R010`） | `outputs/competitor-insights/BCI-004/20261107-r046-verify/` |
| D7c | 枚举取值归一集中层（L12） | 完成（2026-11-07） | 新增 `server/value_normalizer.py`（唯一归一处：空值/无数据标记 → `no_value`；否定 → `unknown`；多片段 → `ambiguous`/`normalized`；单片精确 → `exact`，去修饰前缀或唯一包含 → `normalized`）；`archive_generator._tag_field` 的 enum 分支改为调用归一层：`no_value`→`fill_mode=none`+`missing`、`ambiguous`→`no_data_reason`+`suspect`（不取第一个值）、`unknown`→`invalid_enum` 整人失败、`normalized` 写 `source_ref.normalized_from/normalized_rule`。全库扫描 63 条：「换购。」31/「增购。」20/「首购。」10 直通，「实际增购。」1 → 增购（用户拍板），「换购；增购。」1 → suspect（R046 已按原文人工修正）。只读联调：R063 生成 `增购`+归一记录，R046 生成 `suspect`+原因。新增 `tests/test_value_normalizer.py` 9 项，全量 90/90 通过 | `outputs/competitor-insights/BCI-004/20261107-enum-normalize/` |
| D7d | 互斥回退与渠道归并（用户确认） | 完成（2026-11-07） | ① 互斥多值回退 `interview.purchase_type`：与候选唯一一致才取值、`review_status=ok`、`source_ref.correction` 记原标签值/元数据/规则名/依据；缺失或冲突保持 `suspect`，重跑 R046 不再打回 suspect（实测增购+ok）。② `info_channels` 呈现层归并：归并表 `templates/info_channel_aliases.json` 覆盖全库 64 种写法（原报告 66 为同值内重复计数，已更正），逐条含原写法/目标渠道/次数/依据；未收录写法落「未归类」不丢弃；原始写法完整保留在 `source_ref.raw_values/raw_parts`。新增单测 14 项，全量 104/104 | `outputs/competitor-insights/BCI-004/20261107-channel-normalize/` |
| D8 | 浏览器验收 | 完成（2026-11-07） | 真实服务（127.0.0.1:7861，不动 7860）+ 真实库 + Playwright：63 人列表、R003 43 维、8 个无来源维、R010 9 分、R003 评分缺失、找原话 50 条、勾选 2 人下载 xlsx（45 行/3 Sheet/证据页含两人）、模板切换后重载、0 JS 错误，共 18/18 PASS | `outputs/competitor-insights/BCI-004/20261107-d8-browser/check.log` |
| S5 | 模板注册与校验 | 由 D1 承接 | 方案 §3.4 已给规则 | 见 §10 |
| S6 | 存储层与生成器 | 由 D2/D3 承接 | 方案 §2、§4 已给契约 | 见 §10 |
| S7 | 接口与前端 | 由 D4/D5/D6 承接 | 方案 §4、§5 | 见 §10 |
| S8 | 导出与浏览器验收 | 由 D4/D7/D8 承接 | 方案 §5.5、§7 | 见 §10 |

> 步骤编号说明：S0–S4 为方案与实测阶段（已完成）；D0–D8 为开发阶段（见 §10），S5–S8 已并入 D1–D8，不再单独执行。

## 4. 关键决策摘要

1. 档案存 PostgreSQL 长表：`bci.archive` + `bci.archive_field`，一维一行；模板版本与模板快照随档案保存，升级不覆盖旧档案。
2. 模板驱动：表头/分组/类型/校验来自模板 JSON；维度 → 题号/标签/元数据字段的映射放独立 `source-map.json`，不改模板本体。
3. 生成确定性优先：能由 `interview` 元数据或 `tag` 直取的维度不调用模型；只有综合类维度走 LLM。
4. 反幻觉硬门：LLM 只返回候选证据 ID，原话由服务端截取；证据不属于该受访者则该字段判失败。
5. 导出为真 `.xlsx`（openpyxl）与单人 `.md`，内存返回，不落 `outputs/`、不做伪 `.xls`。
6. v1 不做自由指令解析，用明确按钮替代原型的假指令/假进度。
7. 已拍板：Q1 建 `bci` schema + 4 表；Q2 自动生成 + 只读；Q9 先 10 人试点。
8. 8 个无来源维度显示「本期无来源」+ 具体原因，不补题、不补访、不补全（Q11 已拍板）。
9. 满意度评分只对 13 位有明确分数者生成，其余醒目提示实际情况（Q12 已拍板）。
10. 开发分两段：D1–D5 只新增文件；D6 起才改共用文件，且需用户确认「入库完成」。

## 5. 已核对的工程事实

- 页面：`home.html` 的 bci 视图已存在 4 个 tab，`profile` 当前是占位；tab 切换由 `bci.js` 的事件委托完成，启用只需去 `disabled` 并补 panel。
- scope：`bci.js` 写入 `localStorage['bci.scope']`、`window.BCI_SCOPE`，并派发 `bci:scope-applied`；结构为 `version + datasources{quant_structured, interview_parsed, insight_template, flow_data}`。
- 模板：`templates.json` 现有两条 `ready`（`nev_user_insight`、`user_insight_archive`），均为 43 维；均无题项映射字段。
- 数据（2026-11-06 只读实测）：63 人、85 题、85 个 distinct 标签、`answer` 5355、`evidence` 81437、`tag` 5355、`tag_evidence` 45244。`interview` 无姓名/年龄/性别/收入列，`metadata` 也不含人口统计；63 人无埃安车型；全库仅 3 人提及埃安；Q59 有明确数字分者 13 人。
- 标签质量：`extraction_status` 中 `not_asked` 1017 行、`not_applicable` 302 行；`trust_status≠可信` 623 行（不适用 252 + 真实不可信 371）；`放弃原因` 仅 21/63 可信、`购车动机` 45/63 可信。
- 服务：`app.py` 使用 `ThreadingHTTPServer`，`HOST=0.0.0.0`、`PORT=7860`；`/api/insight/*` 无鉴权；导出需要新增二进制响应方法，不能复用 `_send_file`。
- 依赖：`openpyxl`、`jsonschema`、`psycopg2` 均已在当前 Python 环境可用。

## 6. 交付文件

**新增**

- `competitor_insight/docs/archive-tab-design.md`（方案正文，v2 已含实测）
- `competitor_insight/docs/coverage.csv`（43 维覆盖率，43 行）
- `competitor_insight/tasks/BCI-004/TASK.md`（本文件）
- `outputs/competitor-insights/BCI-004/20261106-archive-design/db-probe.log`
- `outputs/competitor-insights/BCI-004/20261106-archive-design/manifest.json`
- `outputs/competitor-insights/BCI-004/20261106-coverage/`（manifest、coverage.py、4 份日志）
- `competitor_insight/templates/user_insight_archive.source-map.json`（43 维映射，D1）
- `competitor_insight/server/source_map.py`、`server/template_registry.py`（D1）
- `competitor_insight/server/db.py`、`server/archive_store.py`（D2）
- `competitor_insight/server/evidence_gate.py`、`server/archive_generator.py`（D3）
- `competitor_insight/server/archive_api.py`、`server/quote_service.py`、`server/export_service.py`（D4）
- `competitor_insight/web/bci-profile.js`、`web/bci-profile.css`（D5）
- `competitor_insight/tests/__init__.py`、`tests/test_source_map.py`（D1，23 项）、`tests/test_archive_store.py`（D2，9 项）、`tests/test_archive_generator.py`（D3，24 项）、`tests/test_archive_service.py`（D4，25 项）
- `ops/bci_archive_ddl_owner.sql`、`ops/bci_archive_ddl.sql`、`ops/apply_bci_archive_ddl.py`（D2，可重复执行）
- `outputs/competitor-insights/BCI-004/20261107-d1-sourcemap/`（题号/标签探查、库侧校验、权限探查与日志）
- `outputs/competitor-insights/BCI-004/20261107-d2-ddl/apply.log`（建表前后权限、结构、约束、索引、冒烟结果）
- `outputs/competitor-insights/BCI-004/20261107-d3-generator/`（`probe_schema_d3.py`、`probe_tag_values.py`、`probe_generate.py` 与 3 份日志）
- `outputs/competitor-insights/BCI-004/20261107-d4-api/`（`probe_api.py`、`probe.log`、`manifest.json`）
- `outputs/competitor-insights/BCI-004/20261107-d5-frontend/`（`fixture.html`、`check_frontend.py`、`check.log`、`profile.png`、`profile-run.png`、`manifest.json`）
- `outputs/competitor-insights/BCI-004/20261107-d6-wiring/`（`probe_wiring.py`、`probe.log`）
- `competitor_insight/server/llm_client.py`（DeepSeek 同步客户端，固定 `api.deepseek.com`，优先读取 `.env` 凭证）
- `outputs/competitor-insights/BCI-004/20261107-d7-pilot/`（`probe_pilot.py`、`pilot.log`）
- `outputs/competitor-insights/BCI-004/20261107-d8-browser/`（`check_d8.py`、`check.log`、`pilot-export.xlsx`、`profile-r003.png`、`profile-r010.png`、`profile-quote.png`、`profile-template-switch.png`）

**修改**

- `competitor_insight/tasks/tasks.md`（新增 BCI-004 行）
- `competitor_insight/BOARD.md`（DEV_DONE 栏新增 BCI-004）
- `competitor_insight/HANDOFF.md`（顶部新增交接条目）
- `competitor_insight/tasks/BCI-003/TASK.md`（两处遗留项的"建议 BCI-004"改为"编号另行确认"，因 BCI-004 已分配给本 tab）
- `competitor_insight/docs/archive-tab-design.md`（D1：§2.1 fill_mode 增加 `derived`；§3.1/§3.2 改为实际契约）
- `app.py`、`home.html`、`competitor_insight/web/bci.js`、`competitor_insight/web/bci-profile.js`（D6 接线：路由、tab 启用、静态引入、按需初始化；均未暂存）

**未改**：`competitor_insight/templates/*.json`（除新增 source-map）、`customer_insight/*`、数据库表结构（D2 已建，D6 只读）。

## 7. Git 状态

- 首次入库已完成：`1bd7eee` 已推送到 `origin/feature/user-insight-t0-t4`。
- 本轮入库：`7dc91aa`（59 个文件，D1–D8 全部新增文件、`ops/` DDL、BCI 文档、`outputs/competitor-insights/BCI-004/` 证据），已推送 `origin/feature/user-insight-t0-t4`。
- `app.py` / `home.html` / `web/bci.js` 只提交竞品洞察相关 hunk：`app.py` 用「HEAD + 4 处 BCI 代码块」构造索引内容（141 行），工作区仍留有深度调研等他处改动，**未纳入本提交**。
- 未纳入（白名单外）：`.gitignore`、`AGENTS.md`、`competitor_insight/tasks/BCI-002/TASK.md`（他任务的 commit_paths 收窄）、`customer_insight/*`、`forecast-engine/*`、`skills/*` 等既有改动。
- `*.log` 按 `.gitignore` 第 20 条不随提交入库：`20261107-d2-ddl/apply.log`、`20261107-d7-pilot/pilot.log`、`20261107-d8-browser/check.log` 等执行日志只留在本机 `outputs/competitor-insights/BCI-004/`。
- 顺带修正：`20261106-coverage/coverage.py` 原硬编码数据库口令已改为读 `.env.new-car`（历史提交中仍可见旧值，见 §8 L11）。

## 8. 遗留问题

| 编号 | 问题 | 影响 | 现状 | 解除条件 | 负责人 | 关联 |
|---|---|---|---|---|---|---|
| BCI-004-L01 | 开放问题 Q5/Q6/Q7/Q10 未答复 | 不阻塞开发；按建议默认实现并在页面留出开关 | Q11/Q12 已拍板；**Q3/Q8 已拍板（2026-11-09：指令输入框不保留、审批流暂不做）**；其余按建议默认 | 用户逐条确认（可延后） | 用户 | 方案 §8.1 |
| BCI-004-L02 | ~~访谈库连接超时~~ 已解除 | — | 2026-11-06 已连通并完成 43 维实测 | 无需处理 | TRAE | `20261106-coverage/` |
| BCI-004-L03 | ~~DDL 已批准但未执行~~ 已解除 | — | 2026-11-07 已建 `bci` schema 与 4 表，loader 可 USAGE/CREATE；结构、约束、索引与冒烟均通过 | 无需处理 | TRAE | `20261107-d2-ddl/apply.log` |
| BCI-004-L10 | ~~`bci` schema 属主为 `vectordb`，不是 `user_insight_loader`~~ 已解除 | — | 2026-11-09 DBA 用 `postgres` 账号执行 `ALTER SCHEMA bci OWNER TO user_insight_loader;` 成功（用户 GUI 实测 240ms）；复跑 `ops/bci_schema_owner.py` 验证：owner=`user_insight_loader`、alter=skipped(already owner)、loader 建表/插入/查询/删除/删表冒烟 **PASS**，业务表 11/473 行读取正常。此前 2026-11-07/11-08 用 `vectordb` 账号 2/2 次失败（42501，两角色均非 superuser、无成员关系，无法自我授权） | 无需处理 | DBA/TRAE | `20261109-owner-close/verify.log`、`20261108-owner-alter/apply.log` |
| BCI-004-L04 | ~~原型「分析指令」输入框不实现~~ 已拍板 | 与原型交互有差异 | 用明确按钮替代 | **2026-11-09 用户拍板：不保留**（若日后要自然语言指令，另立 Agent 意图解析任务） | 用户 | 方案 §8.1 Q3 |
| BCI-004-L05 | 8 维无来源；5 维极稀疏 | 档案出现「本期无来源」行 | **Q11 已拍板**：不补题不补访，标注原因，下周与业务对接；**2026-11-07 用户决定：维持现状（已决策）**，本期不补题、不补访、不改业务口径 | 已决策，无需等待 | 用户/业务 | 方案 §5.7、§6.4 |
| BCI-004-L07 | 性别、同住人数、用户类型、再购车型尺寸 4 个标签全量未提及 | 年龄/性别只能出年龄 | 已实测 0/63 | 按 Q11 原则本期如实标注，下周业务决定是否补题 | 业务 | 方案 §6.2 |
| BCI-004-L08 | 满意度评分仅 13/63 有明确分数 | 该维仅 13 人有值 | **Q12 已拍板**：只对有分数者生成，其余醒目提示实际情况 | 下周与业务对接 | 业务 | 方案 §5.7、§8.1 Q12 |
| BCI-004-L09 | ~~共用文件被另一会话占用~~ 已解除 | — | 2026-11-07 用户确认入库完成（`1bd7eee` 已推送），D6 闸门解除 | 无需处理 | 用户 | 方案 §7.1 |
| BCI-004-L06 | ~~改动未提交 git~~ 已解除 | — | 2026-11-07 已按白名单提交 `7dc91aa` 并推送；`*.log` 受 `.gitignore` 限制仍只在本机；**2026-11-07 用户决定：日志不入库，不修改 `.gitignore`（已决策）**，缺口在 BCI-005-L07 挂账 | 已决策，无需等待 | 用户/TRAE | 本文件 §7、BCI-005-L07 |
| BCI-004-L11 | 历史提交 `1bd7eee` 内的 `20261106-coverage/coverage.py` 曾硬编码数据库口令 | **仓库为公开**（匿名访问 `api.github.com/repos/backstreetdeng/agentscope` 返回 `private=false`、`visibility=public`），且实测历史口令与本机 `.env.new-car` 的 `NEW_CAR_PG_PASSWORD`（即 `vectordb` 账号）**仍然相同**，属有效凭据暴露 | 工作区脚本已改为读 `.env.new-car`，但历史提交无法用普通提交抹除 | **已决策（2026-11-08）：不轮换口令，接受风险**，不再作为待决项；如后续要消除，需轮换或改写历史 | 用户（已决策） | 本文件 §7、GitHub 公开 API 返回 |
| BCI-004-L12 | ~~标签「首增换购属性」存在非标准取值~~ 已解除 | 归一前「实际增购。」会触发 `invalid_enum` 整人失败 | 用户 2026-11-07 拍板「实际增购」算「增购」；D7c 已建集中归一层并接生成器，全库 63 条实测仅 2 条非标准：`实际增购。`→增购（已归一）、`换购；增购。`→suspect（R046 已按原话人工修正） | 无需再决定；D7d 起互斥值回退 `purchase_type` 裁决，R046 重跑稳定为增购/ok（缺失或冲突才 suspect） | TRAE | `20261107-enum-normalize/enum_mapping.md` |

## 9. 阶段流转记录

- 2026-11-06：`CREATED` → `EXECUTING`（用户明确指派 BCI-004，只做方案）。
- 2026-11-06：`EXECUTING` → `DEV_DONE`（方案文档与证据落盘，三方同步完成；无业务代码）。
- 2026-11-06：`DEV_DONE` 维持（增量：Q1/Q2/Q9 决议入档；只读实测 43 维并产出 `coverage.csv`；§6 预判替换为实测；仍未写业务代码、未建表）。
- 2026-11-06：`DEV_DONE` → `EXECUTING`（用户拍板 Q11/Q12 并批准进入开发；共用文件闸门见 §10）。
- 2026-11-07：`EXECUTING` 继续（D1 完成：source-map 契约层 + 23 项单测 + 库侧校验）；用户确认入库完成（`1bd7eee`），D6 闸门解除。
- 2026-11-07：`EXECUTING` 继续（D2 完成：真实库 schema + 4 表 + 存储层，32/32；D3 完成：生成器 + 证据硬门，56/56）。
- 2026-11-07：`EXECUTING` 继续（D4 完成：接口 / 原话 / 导出服务，全量 81/81；真实库只读探针通过，未写库）。
- 2026-11-07：`EXECUTING` 继续（D5 完成：`bci-profile.js/.css` 主体 + 浏览器离线夹具 17/17；模块列按模板分组 `rowspan` 合并；未触碰共用文件）。
- 2026-11-07：`EXECUTING` 继续（D6 完成：路由、tab 启用、静态引入与按需初始化；临时端口探针 19/19，未启动 7860）。
- 2026-11-07：`EXECUTING` 继续（D7 完成：真实 DeepSeek 生成 10 人写库 10/10、183/190 success 维命中；D8 完成：真实服务 + Playwright 18/18）。
- 2026-11-07：`EXECUTING` → `TESTED`（D1–D8 全部完成；单测 81/81、D6 探针 19/19、D8 浏览器 18/18；待用户验收后上线）。
- 2026-11-07：`TESTED` 维持（D7b：R046 购车属性互斥值回原话核实，按家庭口径定为「增购」并保留修正记录；覆盖率 71.05%；发现 R063 非标准标签值，记 L12）。
- 2026-11-07：`TESTED` 维持（D7c：用户拍板「实际增购=增购」，建 `value_normalizer.py` 集中归一并接生成器；全库 63 条仅 2 条非标准，`实际增购。`→增购、`换购；增购。`→suspect；新增单测 9 项，全量 90/90；L12 解除）。
- 2026-11-07：`TESTED` 维持（D7d：用户补两条决定。互斥回退 `purchase_type` 且一致才取值，R046 重跑稳定为增购/ok；`info_channels` 呈现层归并表覆盖 64 种写法、未知落「未归类」、原始写法留 `source_ref`；单测 104/104）。仍待用户决定：① 全量 63 人是否放开（当前保持 10 人试点，代码已就绪）；② `info_channels` 归并口径是否认可（`templates/info_channel_aliases.json` 中「其他/未归类」划线）。
- 2026-11-08：`TESTED` 维持（用户拍板 L10/L11。复测 2026-11-08T23:43:00+08:00 仍为 `42501 must be member of role "user_insight_loader"`，属主未变更，loader 冒烟 PASS、10/430 行读取正常；L10 **未关闭**，转 DBA 一条 SQL。L11 按用户决定**不轮换口令**，记为已决策并从待决清单移除）。
- 2026-11-09：`TESTED` 维持（L10 **解除**：DBA 用 `postgres` 账号执行 ALTER 成功；复跑属主检查与冒烟 PASS，11/473 行读取正常）。
- 2026-11-09：`TESTED` 维持（用户 6 点反馈收口：①Q3 拍板指令输入框不保留、②Q8 拍板审批流暂不做；③列表每行常显状态标记，无档案显示「未生成」；④勾选用户即联动主区域；⑤按钮改名「生成本人档案」且行为改为只生成当前人——原名「生成缺失档案」实为批量补齐全量，防误触发全量费用；⑥找原话确认为「按当前选中受访者检索」，全局检索待用户定。Playwright 7861 验证 5/5 PASS，未动 7860）。
- 2026-11-09：`TESTED` 维持（第二轮反馈：**修复生成器写死 user_insight_archive 的根因**——用户在 NEV 模板下生成 R004 两次均"成功"却写到 user_insight_archive 名下；现在缺 source-map 的模板直接拒绝生成（`template_not_generatable`），前端按钮同步禁用并提示。找原话按用户口径改版：勾选谁查谁（可多选 `= ANY`），未勾选查全部 63 人，结果条目附受访者编号；主按钮换为「生成本人档案」、已生成人禁用（只读）。单测 125/125，Playwright 7861 12/12；R004 的 2 份档案按 user_insight_archive 语义生成、数据有效，保留不删。**后端改动需重启 7860 生效，待用户授权**）。
- 2026-11-09：`TESTED` 维持（用户授权后重启 7860：17820→47064，`/api/health` 与全局找原话接口 200，**全部修复已在 7860 生效**；R004 两行确认为「当前版 + stale 历史修订」的修订机制，用户决定保留。另获长期授权：重启 7860 由执行 AI 自行决定）。

## 10. 开发阶段步骤（2026-11-06 起）

**已拍板约束**：

- Q11：8 个无来源维照常显示，标「本期无来源」+ 具体原因；不补题、不补访、不用模型兜。
- Q12：满意度评分只对 13 位有明确分数者生成；其余留空并显示「访谈中未给出明确评分 / 仅有描述性评价」，醒目色标注。
- 模型只返回证据 ID，原话服务端截取；校验不过整人不落库。
- 批量后台 job，单人最多 2 并发，不占 `AGENT_RUN_LOCK`。
- 10 人试点按 §6.3 名单。

| # | 步骤 | 允许写入 | 依赖 | 验收标准 |
|---|---|---|---|---|
| D0 | 文档同步（Q11/Q12 + 步骤拆分） | `docs/`、`tasks/`、`BOARD.md`、`HANDOFF.md` | 无 | 方案 §5.7/§6.4/§8.1/§7.1 与本文 §10 一致；`check_board.py` 无本任务新错误 |
| D1 | source-map 契约层 | `competitor_insight/templates/user_insight_archive.source-map.json`、`server/source_map.py`、`server/template_registry.py`、`tests/` | D0；`coverage.csv` | 43 维各一条映射；8 个无来源维含 `no_source_reason`；`question_ids` 全部存在于 `question` 表；缺维/重复维/非法题号被拒绝 |
| D2 | 存储层 | `server/db.py`、`server/archive_store.py`、`ops/`（DDL 脚本）、`tests/` | D1；`bci` schema 四表已建 | 幂等 upsert；事务失败不留半份；按模板/版本/状态查询正确；0 行/1 行/多行三态返回不混淆 |
| D3 | 生成器 | `server/archive_generator.py`、`server/evidence_gate.py`、`tests/` | D2 | 19 维直取不调模型；16 维 LLM 只回证据 ID；伪造 ID / 跨人证据 / 非法枚举三类被拒；8 维无来源直接落 `no_data_reason`；单人 fixture 43 行 |
| D4 | 查询/运行/导出服务 | `server/archive_api.py`、`server/quote_service.py`、`server/export_service.py`、`tests/` | D3 | 未挂路由时可直接调模块；xlsx/md 单测通过；无来源行导出为「本期无来源：原因」；评分缺失带 `score_source=missing` |
| D5 | 前端新模块 | `web/bci-profile.js`、`web/bci-profile.css` | D4 | 自包含，不 import `bci.js`；43 行由模板渲染；无来源行与评分缺失行按 §5.7 配色；档案值不进 `innerHTML` |
| D6 | 共用文件接线（闸门） | `app.py`、`home.html`、`bci.js`、`templates.json`、`home.css`、`home.js` | **用户确认「入库完成」** | 路由注册、tab 启用、模板可选；不覆盖另一会话已提交内容 |
| D7 | 10 人试点生成 | 无代码（写库） | D6 | 10 人 × 43 维：19 维全有值；16 维有值或明确无数据；8 维如实显示「本期无来源」；任一 LLM 值无证据 ID 即失败 |
| D8 | 浏览器验收 | 无（只读） | D7 | 单人查看、多人导出、模板切换、无来源行、13 人评分、找原话 6 项断言通过；`check_board.py`、`workspace_hygiene.py` PASS |

**并行与边界**：

- D1–D5 只新增文件，全程不碰 D6 列表里的共用文件，也不启动 7860。
- D2 需要 DDL 先执行；未建表时先做文件后端契约测试，不宣称数据库路径已验收。
- D7 写库属于真实数据写入，执行前确认 `bci` schema 权限已授予。
- 每完成一步更新本文 §3 与 `HANDOFF.md`，不攒到最后。

**执行记录**：

- D1（2026-11-07）：完成。43 维映射齐；fill_mode = tag 22 / metadata 2 / derived 1 / llm 10 / none 8；8 个无来源维均带 `no_source_reason` 且未声明任何来源；61 个题号、56 个标签经真实库校验全部命中；`unittest` 23/23 通过。库侧证据见 `outputs/competitor-insights/BCI-004/20261107-d1-sourcemap/validate.log`。
- D2（2026-11-07）：完成。`vectordb` 建 `bci` schema（`AUTHORIZATION` 因非成员失败，改用最小 `GRANT USAGE, CREATE`），loader 建 4 表并持有；loader 实测 `has_database_create=False`、`has_schema_usage/create(bci)=True`；4 表 + 主键/唯一/外键/CHECK/3 索引 + 序列均核对；插入/查询/级联删除冒烟通过且残留为 0；PG 与文件后端语义一致；全量测试 32/32 通过。证据：`outputs/competitor-insights/BCI-004/20261107-d2-ddl/apply.log`。
- D3（2026-11-07）：完成。新增 `evidence_gate.py`（只索引本受访者、去重、最多 5 条、quote 截 300 字、枚举校验）与 `archive_generator.py`（`PostgresInterviewSource` 只读 5 表；tag/metadata/derived 直取不调模型；llm 维只接受证据 ID）；`tests/test_archive_generator.py` 24 项覆盖 43 行、8 个无来源、三类拒绝、满意度三态与 quote 截断。实现约定：**个人层面无值也落 `fill_mode=none` + `no_data_reason`**，用 `source_ref.no_source_scope` 区分 `template`（本期无来源）与 `interview`（该受访者未提及），避免存储层「非 none 维不得带原因」冲突；`coverage_required` 只统计真实值。真实库只读跑 R003/R001/R002：均 43 维，coverage 68.42/78.95/76.32，R001 满意度 7-8 分取 7.5 并保留区间，R002/R003 落描述性原因。证据：`outputs/competitor-insights/BCI-004/20261107-d3-generator/generate-probe.log`。
- D4（2026-11-07）：完成。`archive_api.py` 提供模板、受访者、详情、生成、轮询、原话、导出，统一 `{"ok":true,"data":...}` / `ApiError`（未挂路由，可直调）；`quote_service.py` 覆盖答案/证据/标签证据/档案值四类检索，`tag_evidence` 经 `JOIN tag` 过滤，关键词转义 `%/_`，读取详情时按 ID 刷新原话、失效标 `source_missing`；`export_service.py` 用 openpyxl 生成三 Sheet（洞察档案 / 口径与证据 / 证据）+ 单人 md，全内存 bytes；无来源维写「本期无来源：原因」，满意度缺分写原因并返回 `score_source=missing`；md 多人返回 `md_single_only`，缺档案返回 `archive_missing` 并列出编号。`tests/test_archive_service.py` 25 项，全量 81/81；真实库只读探针：模板 43 维 / 12 组、63 人、R001 详情空态、找原话命中 5 条。证据：`outputs/competitor-insights/BCI-004/20261107-d4-api/probe.log`。
- D5（2026-11-07）：完成。`web/bci-profile.js`（约 920 行，`window.BciProfile` + `[data-bci-profile]` 自动初始化）与 `web/bci-profile.css`：模板驱动 43 行、模块列按连续同组 `rowspan` 合并、无来源行 `FFF2CC`、满意度缺失 `warn` 行、证据 chip + 原话浮层、找原话四类结果与 `<mark>` 高亮（文本节点拆分，不拼 `innerHTML`）、搜索、生成轮询、xlsx/md 二进制下载、scope 只读（`localStorage` → `BCI_SCOPE` → `bci:scope-applied`，统一按完整 scope 对象解析）。离线 Playwright 夹具（file://，不启 7860、不连库）17 项断言全 PASS，证据 `outputs/competitor-insights/BCI-004/20261107-d5-frontend/`（`check.log` + 两张截图）。发现并修复：`readScope` 返回层级错误导致始终「未选择」；`rowspan` 改造残留 `groupCell` 引用导致渲染中断。Playwright 浏览器改用 `%USERPROFILE%\.cache\ms-playwright`（默认 AppData 路径不存在，已安装 chromium）。
- D6（2026-11-07）：完成。`app.py` 增加 `/api/bci/archive/*`：GET `template/respondents/detail/run/quote`、POST `generate/export`（导出走二进制），`ArchiveService` 惰性单例、`DatabaseUnavailable`→503、`ApiError`→原始状态码，生成走服务自身线程，不触碰 `AGENT_RUN_LOCK`；`home.html` 启用 tab ②、新增 `[data-bci-profile]` 容器与 `bci-profile.css/js`；`bci.js` 仅在切到 tab ② 时 `BciProfile.init`，`bci-profile.js` 面板未展开不预加载。临时端口（非 7860）探针 19/19：模板 43 维/12 组、真实库 63 人、R001 详情空态、`空间` 找原话命中、缺档案导出 409、非法 mode 400、未知接口 404、静态资源与首页接线 PASS。全量单测 81/81。证据：`outputs/competitor-insights/BCI-004/20261107-d6-wiring/probe.log`。
