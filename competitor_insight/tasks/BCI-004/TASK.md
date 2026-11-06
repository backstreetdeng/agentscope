# BCI-004：竞品洞察 · 用户洞察档案 tab

```
task_id: BCI-004
title: 竞品洞察 · 用户洞察档案 tab
stage: EXECUTING
owner: TRAE
commit_paths: competitor_insight/docs/archive-tab-design.md,competitor_insight/tasks/BCI-004,competitor_insight/tasks/tasks.md,competitor_insight/BOARD.md,competitor_insight/HANDOFF.md,outputs/competitor-insights/BCI-004
updated: 2026-11-06
blocked: no
next: 按 §10 执行 D1（source-map 契约层）；共用文件接线需等用户确认「入库完成」
evidence: outputs/competitor-insights/BCI-004/20261106-coverage/
```

## 1. 目标与边界

**目标**：交付「竞品洞察 → 洞察档案」tab 的技术实施方案，并把方案拆成可直接开发、可独立验收的步骤。业务口中的「① 用户洞察档案」= 当前页面 tab ②「洞察档案」（tab ① 已是数据源筛选）；技术标识统一用 `profile`。

**本方案要解决的问题**：一份档案 = 一个受访者 × 模板维度集合（当前两套 ready 模板均为 43 维）。要求：单人查看、多人合并导出、每条结论可回溯原话、模板驱动而非前端写死、真实 `.xlsx` 导出。

**本轮边界**：

- 本轮边界：只做可行性核实与方案修订，**不写业务代码、不建表、不改模板/`templates.json`/`bci.js`/`bci.css`、不启动 7860**。数据库只允许只读 `SELECT`。
- 不改 `home.html`、`app.py`、`customer_insight/*`；开发阶段的改动范围在方案 §1.1 列明。
- 不自行扩展需求：不做车型矩阵、不做评分推荐、不做自由指令 Agent、不做多人并排查看。
- 不编数据：所有数字必须来自只读 SQL 实测，文件推断与实测分开标注（`coverage.csv` 有 `evidence_basis` 列）。
- 已定决策：Q1 批准建 `bci` schema + 4 表；Q2 模型自动生成 + 只读；Q9 先 10 人试点。

**允许写入（本轮）**：`competitor_insight/docs/archive-tab-design.md`、`competitor_insight/docs/coverage.csv`、`competitor_insight/tasks/BCI-004/TASK.md`、`tasks/tasks.md`、`BOARD.md`、`HANDOFF.md`、`outputs/competitor-insights/BCI-004/`。

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
| S5 | 模板注册与校验（S2 步骤） | 未做 | 方案 §3.4 已给规则 | 无 |
| S6 | 存储层与生成器（S3/S4） | 未做 | 方案 §2、§4 已给契约 | 无 |
| S7 | 接口与前端（S5–S7） | 未做 | 方案 §4、§5 | 无 |
| S8 | 导出与浏览器验收（S8/S9） | 未做 | 方案 §5.5、§7 | 无 |

> 步骤编号说明：本表 S0–S3 是本轮方案阶段；S4–S8 对应方案 §7 的开发步骤组，方案确认后再展开为细项。

## 4. 关键决策摘要

1. 档案存 PostgreSQL 长表：`bci.archive` + `bci.archive_field`，一维一行；模板版本与模板快照随档案保存，升级不覆盖旧档案。
2. 模板驱动：表头/分组/类型/校验来自模板 JSON；维度 → 题号/标签/元数据字段的映射放独立 `source-map.json`，不改模板本体。
3. 生成确定性优先：能由 `interview` 元数据或 `tag` 直取的维度不调用模型；只有综合类维度走 LLM。
4. 反幻觉硬门：LLM 只返回候选证据 ID，原话由服务端截取；证据不属于该受访者则该字段判失败。
5. 导出为真 `.xlsx`（openpyxl）与单人 `.md`，内存返回，不落 `outputs/`、不做伪 `.xls`。
6. v1 不做自由指令解析，用明确按钮替代原型的假指令/假进度。
7. 已拍板：Q1 建 `bci` schema + 4 表；Q2 自动生成 + 只读；Q9 先 10 人试点。
8. 8 个无来源维度（KOL、首选率、RT 四维、接待期待、老车主复购）显示「无数据（未问到）」，不补全。

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

**修改**

- `competitor_insight/tasks/tasks.md`（新增 BCI-004 行）
- `competitor_insight/BOARD.md`（DEV_DONE 栏新增 BCI-004）
- `competitor_insight/HANDOFF.md`（顶部新增交接条目）
- `competitor_insight/tasks/BCI-003/TASK.md`（两处遗留项的"建议 BCI-004"改为"编号另行确认"，因 BCI-004 已分配给本 tab）

**未改**：`home.html`、`app.py`、`competitor_insight/web/*`、`competitor_insight/templates/*`、`customer_insight/*`、数据库（只读 SELECT）。

## 7. Git 状态

- 全部改动**未提交、未暂存**。
- 工作区同时存在其他任务的大量未提交改动（`app.py`、`home.html`、`customer_insight/*`、`forecast-engine/*` 等），不得整体暂存，也不得把其他任务改动记入本任务。
- 本轮未执行 `git add` / `commit` / `push`。

## 8. 遗留问题

| 编号 | 问题 | 影响 | 现状 | 解除条件 | 负责人 | 关联 |
|---|---|---|---|---|---|---|
| BCI-004-L01 | 开放问题 Q3/Q5/Q6/Q7/Q8/Q10 未答复 | 不阻塞开发；按建议默认实现并在页面留出开关 | Q11/Q12 已拍板；其余按建议默认 | 用户逐条确认（可延后） | 用户 | 方案 §8.1 |
| BCI-004-L02 | ~~访谈库连接超时~~ 已解除 | — | 2026-11-06 已连通并完成 43 维实测 | 无需处理 | TRAE | `20261106-coverage/` |
| BCI-004-L03 | DDL 已批准但尚未执行 | 存储层无法落库测试 | Q1 已批准 | 开发 D2 前由有 DDL 权限的账号执行 §2.1 | 用户/TRAE | 方案 §2.1 |
| BCI-004-L04 | 原型「分析指令」输入框不实现 | 与原型交互有差异 | 方案建议用明确按钮替代 | 用户确认；若要保留则另立 Agent 意图解析任务 | 用户 | 方案 §8.1 Q3 |
| BCI-004-L05 | 8 维无来源；5 维极稀疏 | 档案出现「本期无来源」行 | **Q11 已拍板**：不补题不补访，标注原因，下周与业务对接 | 下周业务沟通 | 用户/业务 | 方案 §5.7、§6.4 |
| BCI-004-L07 | 性别、同住人数、用户类型、再购车型尺寸 4 个标签全量未提及 | 年龄/性别只能出年龄 | 已实测 0/63 | 按 Q11 原则本期如实标注，下周业务决定是否补题 | 业务 | 方案 §6.2 |
| BCI-004-L08 | 满意度评分仅 13/63 有明确分数 | 该维仅 13 人有值 | **Q12 已拍板**：只对有分数者生成，其余醒目提示实际情况 | 下周与业务对接 | 业务 | 方案 §5.7、§8.1 Q12 |
| BCI-004-L09 | 共用文件（`app.py`/`home.html`/`bci.js`/`templates.json`/`home.css`/`home.js`）被另一会话占用 | 前端接线与浏览器验收需等待 | 先做纯新增文件 | 用户确认「入库完成」 | 用户/另一会话 | 方案 §7.1 |
| BCI-004-L06 | 改动未提交 git | 成果只在工作区 | 另一会话正在做首次入库 | 用户授权后按文件粒度提交 | 用户/TRAE | 本文件 §7 |

## 9. 阶段流转记录

- 2026-11-06：`CREATED` → `EXECUTING`（用户明确指派 BCI-004，只做方案）。
- 2026-11-06：`EXECUTING` → `DEV_DONE`（方案文档与证据落盘，三方同步完成；无业务代码）。
- 2026-11-06：`DEV_DONE` 维持（增量：Q1/Q2/Q9 决议入档；只读实测 43 维并产出 `coverage.csv`；§6 预判替换为实测；仍未写业务代码、未建表）。
- 2026-11-06：`DEV_DONE` → `EXECUTING`（用户拍板 Q11/Q12 并批准进入开发；共用文件闸门见 §10）。

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
