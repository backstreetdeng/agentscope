# BCI-002：深访用户洞察档案模板（两份：新能源 / 用户洞察档案）

```
task_id: BCI-002
title: 深访用户洞察档案模板（两份：新能源 / 用户洞察档案）
stage: TESTED
owner: TRAE
commit_paths: competitor_insight/templates/nev_user_insight_template.json,competitor_insight/templates/nev_user_insight_template.md,competitor_insight/templates/user_insight_archive_template.json,competitor_insight/templates/user_insight_archive_template.md,competitor_insight/templates/README.md,competitor_insight/web/templates.json,competitor_insight/docs/template-vs-prototype-mapping.md,competitor_insight/tasks/BCI-002,outputs/competitor-insights/BCI-002
updated: 2026-11-06
blocked: no
next: 用户验收 7860 页面下拉两条模板均可选后确认上线
evidence: outputs/competitor-insights/BCI-002/20261106-template-v1/
```

## 1. 目标与边界

**目标**：产出可实际装数据的《深访用户洞察档案模板》，并让它们在竞品洞察 tab ①「深访用户洞察档案模板」下拉中**可选中**；选中后写入 `bci.scope.datasources.insight_template`。范围已扩为**两份并存**：

| 模板 | 标识 | 结构基线 | 状态 |
|---|---|---|---|
| 新能源用户洞察模板 | `nev_user_insight` | 埃安RT 本竞品用户洞察报告 P1–P11 | ready（8 组 43 维） |
| 用户洞察档案模板 | `user_insight_archive` | 交互原型第 386 行 `P.TROWS` 43 维表 | ready（12 组 43 维） |
| 新车型用户洞察模板 | `new_model_user_insight` | 业务未提供 | pending（等业务） |

**依据**：`D:\work\AI\用户洞察智能体\用户洞察开发基线\埃安RT_本竞品用户洞察报告.html`（P1–P11）+ 原型 `目标车型本竞品洞察智能体_交互原型v2.html` 第 386 行 `P.TROWS`。

**边界**：

- 模板是**能装数据的结构**（维度 + 类型 + 必填 + 合格标准 + 示例），不是占位说明。
- `nev_user_insight` 已验收，**一个字未改**；第二份模板独立文件、独立 id，不覆盖、不复用其维度。
- 示例只作"填成什么样算合格"，不进入 schema。
- 前端不写死模板列表：清单放 `competitor_insight/web/templates.json`，新增模板不改 JS。
- 新车型模板继续「待提供」，原因写明「待业务提供模板文件，不是开发待办」。

**允许写入**：`competitor_insight/templates/`（模板定义 + 说明）、`competitor_insight/web/templates.json`（下拉清单）、`competitor_insight/web/bci.js`（只改模板选项加载方式）、`competitor_insight/docs/`（核对文档）、`competitor_insight/` 内任务与看板文档、`outputs/competitor-insights/BCI-002/` 证据。

### 入库判定（commit_paths）的边界 — 2026-11-07 声明收窄

原声明把 `competitor_insight/templates` 整目录算进来。但该目录已被 BCI-004 用来写 `user_insight_archive.source-map.json`（其允许写入范围明确包含 `templates/*.source-map.json`），整目录声明会让别人的在途文件持续把本任务判红。按「谁生成谁声明」改为具体文件，**这是声明层面的归属修正，不是为了变绿**：

| 路径 | 处理 | 原因 |
|---|---|---|
| `competitor_insight/templates/`（整目录） | **改为逐个文件** | 共享目录；BCI-004 正在写 `*.source-map.json`，不属本任务 |
| `competitor_insight/web/bci.js` | **移出** | 与 BCI-001 共用（本任务只改模板选项加载，BCI-001 负责模块主体与 `bci.scope`） |
| 4 份模板 + `templates/README.md` | 保留 | 本任务产出并独占 |
| `competitor_insight/web/templates.json` | 保留 | 本任务产出的下拉清单（单文件，不整目录声明 `web/`） |
| `competitor_insight/docs/template-vs-prototype-mapping.md` | 保留 | 本任务产出的核对文档（具体文件） |

**盲区**：`templates/README.md` 若日后被别的任务改写，本检查会判红；届时应改由实际改动方声明，或按本表方式再收窄。本任务今后若再改 `bci.js`，需人工登记，自动检查不再覆盖。

## 2. 交付结构（对照埃安RT 报告）

模板以**维度**为最小单位（后端要按维度校验档案），8 个分组映射报告章节：

| 分组 ID | 分组名 | 报告章节 | 维度数 |
|---|---|---|---|
| `basic_profile` | 基本信息与画像 | P1 | 9 |
| `purchase_decision` | 购车关注与决策 | P4 / P10 | 7 |
| `user_source` | 用户来源与增换购 | P2 / P3 | 5 |
| `competitor_compare` | 本竞品对比与首选 | P5 / P6 | 5 |
| `satisfaction` | 满意度与进攻方向 | P7 | 4 |
| `channels` | 信息渠道 | P8 | 5 |
| `attraction` | 本品吸引力 | P9 | 3 |
| `conversion` | 转化机会与风险 | P10 | 5 |

合计 **43 维**（必填 28、选填 15）。

三处对报告的合并/取舍，需下游知道：

- **P2/P3 合并为 `user_source`**：两章是"不同竞品来源"同一套字段（前车能源/级别/品牌/属性），逐车型重复建维度会在单用户档案里产生冲突；聚合占比留在报告层，不入单用户档案。
- **P11 小结不建维度**：它是前 10 章的汇总，不引入新数据；由后端按分组聚合生成。
- **P6「首选率」按单用户口径落成 `first_choice_model`**：报告里的百分比是聚合值，单用户档案只记"此人首选哪台"。

## 2.2 第二份模板结构（对照原型 `P.TROWS`）

用户 2026-11-06 决定：**不改第一份模板，另做一份对齐原型档案表的模板**。维度名与顺序以原型第 386 行 43 行为准，模块分组以用户梳理表为准：

| 模块 | 维度数 | 与原型分组的关系 |
|---|---|---|
| 用户简要总结 | 1 | 原型该行无子项名，取组名为维度名 |
| 用户画像 | 6 | 一致 |
| 拥车与购车情况 | 5 | 一致 |
| 购车考虑 | 2 | 一致 |
| 购车关注 | 4 | 一致 |
| 信息渠道 | 3 | 一致 |
| 购车对比 | 7 | **合并**原型 3 组（购车对比 2 + 已购下定及战胜原因 3 + 放弃车型及战败原因 2） |
| 对埃安品牌的印象和了解（网约车的影响） | 1 | 一致 |
| 对埃安RT的认知与态度 | 5 | 一致（含转化机会/风险） |
| 用车场景 | 4 | 一致 |
| 满意度评价 | 4 | 原型该组 5 项，其中老车主再购被拆出 |
| 作为埃安老车主 为什么继续再买埃安的车 | 1 | **拆出**为独立模块 |

合计 **12 组 43 维**（必填 38、选填 5）。子项名称与顺序经脚本逐位比对：**43/43 与原型完全一致，无改名、无合并**。

## 3. 交付物

| 文件 | 内容 |
|---|---|
| `competitor_insight/templates/nev_user_insight_template.json` | 机器可读定义：8 组 43 维，每维含 `id/name/group/type/required/description/qualified`，枚举/多选带 `options` |
| `competitor_insight/templates/nev_user_insight_template.md` | 人读版：模板标识、43 维总表、逐维填写说明与合格标准、埃安RT 片段示例（标 P 编号）、版本记录 |
| `competitor_insight/templates/README.md` | 新增模板流程、版本管理、前后端读取方式 |
| `competitor_insight/web/templates.json` | 下拉清单：`nev_user_insight`(ready) + `new_model_user_insight`(pending + 原因) |
| `competitor_insight/web/bci.js` | `insight_template` 选项改为运行时读清单；`enter()` 先加载清单再 `restore()` |
| `competitor_insight/templates/user_insight_archive_template.json` | 第二份模板机器可读定义：12 组 43 维，字段同第一份 |
| `competitor_insight/templates/user_insight_archive_template.md` | 第二份模板人读版：与原型 43 项对齐校验、维度清单、柏君谕案例填写示例 |
| `competitor_insight/docs/template-vs-prototype-mapping.md` | 两套模板与原型的逐项映射；第二份模板的正确性校验结论 |
| `competitor_insight/web/templates.json` | 下拉清单：两份 ready + 新车型 pending |

## 4. 验收标准

| # | 验收项 | 判定方式 |
|---|---|---|
| A1 | 模板标识齐全：名称、ID、版本 v1、状态、适用场景、结构基线 | 检查 JSON 顶层字段与 md 第 0 节 |
| A2 | 维度清单 43 项、8 组，每维含维度名、分组、取值类型、是否必填 | 校验 JSON `dimensions` 长度与字段完整性 |
| A3 | 取值类型限定在 text/enum/multi/number/date；enum/multi 必带 `options` | 校验器逐维检查 |
| A4 | 每个维度都有 `description`（填写说明）与 `qualified`（合格标准） | 校验器逐维非空检查 |
| A5 | md 含一份标注来源的埃安RT 片段示例，且与 JSON 同源可对账 | 校验器核对 md 是否覆盖全部维度名与分组 ID |
| A6 | 下拉中「新能源用户洞察模板」可选，选中后 `bci.scope.datasources.insight_template === "nev_user_insight"` | 浏览器断言 + 读 localStorage |
| A7 | 「新车型用户洞察模板」不可选，原因写明是等业务提供、不是等开发 | 断言 disabled + 原因文案含「业务提供」 |
| A8 | 模板列表不写死在前端：`bci.js` 不含具体模板名/待生成文案，清单来自 `templates.json` | 静态检索 + 浏览器请求 `templates.json` 成功 |
| A9 | 清单加载失败时不伪造正常列表，只给不可选降级项并说明 | 代码路径检查（`.catch` 分支） |
| A10 | 无 JS 运行时错误 | 捕获 `pageerror` / console error |
| A11 | 第二份模板 43 维、12 组，名称与顺序与原型 `P.TROWS` 逐位一致（0 处改名/合并） | 脚本比对原型第 386 行导出清单与新模板 `dimensions[].name` |
| A12 | 第二份模板每维含 `description` 与 `qualified`；`id` 全局唯一；`group` 无悬空引用 | 脚本校验 |
| A13 | 下拉同时列出两条 ready 模板，「用户洞察档案模板」可选，选中后 `bci.scope.datasources.insight_template === "user_insight_archive"` | 浏览器断言 + 读 localStorage |
| A14 | `nev_user_insight` 未被改动 | 与 BCI-002 首轮验收的 JSON 内容比对（字段与维度名不变） |

## 5. 步骤与结果

| # | 步骤 | 状态 | 实际结果 |
|---|---|---|---|
| S1 | 登记任务与范围 | 完成 | 本文件；原「本轮不产出正文」已被 2026-11-06 用户提优先级覆盖 |
| S2 | 抽取埃安RT 报告章节结构与字段 | 完成 | P1–P11 章节与各表表头已解析，纯文本导出见 `temp/20261106-bci/rt_sections.txt` |
| S3 | 产出入库维度定义（JSON） | 完成 | 8 组 43 维，必填 31 / 选填 12 |
| S4 | 产出人读模板与列表清单 | 完成 | `nev_user_insight_template.md`、`templates/README.md`、`web/templates.json` |
| S5 | 前端接线：改 `bci.js` 读清单 | 完成 | 新增 `templateOptionsFrom()` / `loadTemplates()`；`enter()` 改先 `await` 清单再 `restore()`，避免已存选择被 options 过滤丢失 |
| S6 | 自查 A1–A5、A8–A9 | 完成 | `outputs/competitor-insights/BCI-002/20261106-template-v1/validate_template.py` 全部通过 |
| S7 | 浏览器验收 A6/A7/A10 | 完成 | 复用 BCI-001 验收脚本，新增模板可选断言；见证据索引 |
| S8 | 用户验收 | 待做 | 见状态块 `next` |
| S9 | 用户质疑"模板是不是照原型 43 维表做的" → 逐项核对 | 完成 | 原型第 386 行 43 行导出；与 `nev_user_insight` 逐项映射：8 一致 / 13 语义同 / 7 半覆盖 / 15 原型独有 / 8 我方独有。结论：`nev_user_insight` 按报告 P1–P11，不是照原型；结构不一致。文档 `docs/template-vs-prototype-mapping.md` |
| S10 | 用户决定另做第二份模板 → 产出 `user_insight_archive` | 完成 | 12 组 43 维；脚本逐位比对原型子项名：43/43 一致；id 唯一、group 无悬空；`nev_user_insight` 未改 |
| S11 | 登记进下拉清单 | 完成 | `web/templates.json` 两条 ready + 新车型 pending；`bci.js` 无需改动（本就运行时读清单） |

## 6. 证据索引

- `outputs/competitor-insights/BCI-002/20261106-template-v1/validate_template.py`：模板结构与前端接线校验脚本（可重跑，退出码 0 = 全通过）
- `outputs/competitor-insights/BCI-002/20261106-template-two/validate_archive_template.py`：第二轮校验（原型 43 项逐位比对 + 清单规则），`validate.log` 记录 `43/43 一致 / 12 组 / 必填 38 / PASS`
- `outputs/competitor-insights/BCI-002/20261106-template-two/screenshots/template-dropdown-expanded.png`：7860 页面下拉展开截图，三条模板状态可见
- 浏览器断言：两条 ready 可选、新车型 disabled 且文案「待业务提供」；选中档案模板后 `localStorage.bci.scope.datasources.insight_template = "user_insight_archive"`
- `outputs/competitor-insights/BCI-002/20261106-template-v1/validate.log`：校验输出
- `outputs/competitor-insights/BCI-002/20261106-template-v1/manifest.json`：产物清单与用途
- 浏览器证据：`outputs/competitor-insights/BCI-001/20261106-datasource-selector-r2/`（`verify.log`、`screenshots/`）
- 结构基线原始导出：`temp/20261106-bci/rt_sections.txt`（可重建）

## 7. 遗留问题

| 编号 | 问题 | 影响 | 现状 | 解除条件 | 负责人 | 证据/关联 |
|---|---|---|---|---|---|---|
| BCI-002-L01 | 新车型用户洞察模板缺失 | 该项仍不可选 | 业务未提供 | 业务提供模板文件后按 `templates/README.md` 登记为 ready | 用户/业务 | BCI-001-L02 |
| BCI-002-L02 | 模板仅定义维度，尚无后端校验器消费 | 档案写入时不会被自动判合格 | 仅 JSON 定义可用 | 档案写入接口落地时按 `dimensions` 实现必填与类型校验 | TRAE | `nev_user_insight_template.json` |
| BCI-002-L03 | ~~改动未提交 git~~ 已解除 | — | **已关闭**（2026-11-07）：模板与清单随 `1bd7eee` 入库并推送，声明收窄 `f432794`；`check_board.py` PASS | 已完成 | TRAE | `git log`、本文件 §1 入库判定边界 |
| BCI-002-L04 | 第二份模板的模块分组与原型不完全同构（购车对比合并 3 组、老车主再购拆出） | 若上游要求"严格 13 组"，档案表分组需再调 | 按用户梳理表执行，未自行改动 | 业务确认档案表要 12 组还是原型 13 组；若要 13 组，拆 `comparison` 并把 `loyal_repurchase` 并回 `satisfaction` | 用户/业务 | `docs/template-vs-prototype-mapping.md` §6 |
| BCI-002-L05 | 原型第 386 行 15 列只用了前 2 列，取值类型/必填/合格标准为新写 | 「购车属性」等字段的口径可能与业务问卷不一致 | 已标推断 | 收到业务问卷或填写规范后逐维核对 | 业务 / TRAE | 同上 §6 末段 |
| BCI-002-L06 | 「① 洞察档案」tab 仍未开发 | 下拉选了模板也没有消费方，档案表无法展示 | **已由 BCI-004 实现（`TESTED`，2026-11-07 入库）**，本项转为待用户验收；模板可被其真实读取 | 用户验收 BCI-004 后关闭 | TRAE | BCI-001-L05、[BCI-004](BCI-004/TASK.md) |

## 8. 阶段流转记录

| 日期 | 阶段 | 依据 | 证据 | 变更人 |
|---|---|---|---|---|
| 2026-11-06 | CREATED | 用户要求模板作为独立交付物单独建任务，当时只登记范围 | 本文件 | TRAE |
| 2026-11-06 | CREATED → EXECUTING | 用户提优先级：页面显示「尚未产出，已立 BCI-002」是错的，要求立即产出 v1 并让下拉可选 | 本文件第 1 节 | 用户要求 / TRAE |
| 2026-11-06 | TESTED（第一轮） | 模板 JSON/md/README、下拉清单、前端清单加载全部完成；静态校验与浏览器断言通过 | `20261106-template-v1` | TRAE |
| 2026-11-06 | TESTED → EXECUTING（范围扩大） | 用户质疑模板是否照原型 43 维表做；核对后确认不是，用户决定另做第二份模板并对齐原型 | `docs/template-vs-prototype-mapping.md` | 用户决定 / TRAE |
| 2026-11-06 | EXECUTING → TESTED（第二轮） | 第二份模板 12 组 43 维，原型子项 43/43 逐位一致；清单两条 ready；7860 下拉两条可选且选择落 `bci.scope` | `20261106-template-two` | TRAE |
| — | LIVE | 待用户验收确认 | — | 待定 |
