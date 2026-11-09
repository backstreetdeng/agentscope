# BCI-001：竞品洞察 · 数据源筛选 tab

```
task_id: BCI-001
title: 竞品洞察 · 数据源筛选 tab
stage: TESTED
owner: TRAE
commit_paths: competitor_insight/web/bci.js,competitor_insight/web/bci.css,competitor_insight/tasks/BCI-001,outputs/competitor-insights/BCI-001,assets/home.js
updated: 2026-11-06
blocked: no
next: 用户验收 7860 页面后确认上线
evidence: outputs/competitor-insights/BCI-001/20261106-datasource-selector-r2/
```

## 1. 目标与边界

**目标**：左侧导航一级「竞品洞察」下，第一个 tab【数据源筛选】只做一件事——**为本次分析选择数据源与模板**。前提是后台已完成标准化数据与洞察档案模板的接入；四类各一个下拉，默认全部「不选」，不选即该类数据不参与后续洞察。

**边界**：

- 只做 tab ①；tab ②③④ 仅骨架占位，不可点。
- 不做车型维度、不做可用性评分、不做"智能推荐"；业务没说的不做。
- 不改既有市场分析、市场预测、用户洞察、竞品对标（MKT-001）的接口契约与页面行为。
- 不替业务预设下游怎么用：只把选择结果落成可读作用域，不规定消费方式。

**允许写入**：`competitor_insight/web/bci.js`、`competitor_insight/web/bci.css`、`home.html`（视图骨架与资源引用）、`app.py`（仅 `/competitor-insight/` 静态路由与白名单）、`competitor_insight/` 内的任务与看板文档（`tasks/`、`BOARD.md`、`HANDOFF.md`、`docs/root-files.json`、`forecast-engine/share-files/` 的指针）。

## 2. 口径纠正（2026-11-06，用户驳回后重做）

**错在哪**：上一版把「数据源筛选」理解成了「5 台车 × 5 类数据的可用性体检」，因此做了 5×5 车型可用性矩阵、按车型的空样本告警与降级建议，还把"选择"绑成车型集合。这是自行扩展需求：页面实际没有"车型维度"这一层，业务也只要求选数据源与模板。

**正确口径**：该 tab 的前提是**后台已完成全部标准化数据与洞察档案模板的接入**，页面只负责**为本次分析选择数据源与模板**。四类各一个下拉，**默认全部「不选」**，不选 = 该类数据不参与后续洞察：

| 类别 | 选项 | 当前状态 |
|---|---|---|
| 定量结构化数据 | 2023 / 2024 / 2025 三年，可单选可多选 | 三年源文件结构已核对；仅 2025 年已入库 |
| 定性深访解析数据 | 2025年_定性解析、2026年_定性解析 | 只有 2025（63 人）；2026 音频未解析，不可选 |
| 深访用户洞察档案模板 | 新能源用户洞察模板、新车型用户洞察模板 | 两套均不存在：新能源待 BCI-002 产出，新车型待业务提供 |
| 流通数据（增换购流转分析） | 增换购流转分析 | 当前没有，待业务提供 |

**已按纠正删除**：5×5 可用性矩阵、车型 chip、空样本告警与降级建议、`customer_insight/datasource_service.py`、`POST /api/bci/datasource/availability` 及其 `do_POST` 白名单项（该接口只服务上述错误用途）。

**保留**：`bci.scope` 作用域契约思路——选择结果写入 `localStorage['bci.scope']`，同时挂 `window.BCI_SCOPE` 并派发 `bci:scope-applied` 事件，供后续 tab 读取。

## 3. 验收标准（可判定）

### 用户验收反馈（2026-11-06）

| 反馈 | 处理 | 结果 |
|---|---|---|
| 四类数据源卡片应为「两行两列（2×2）」，当前是四行一列；窄屏回落单列，只调布局、不改内容与交互 | 改 `competitor_insight/web/bci.css`：`.bci-groups` 由纵向 flex 改为 2 列 grid，`grid-auto-rows: 1fr` 保证等宽等高，行距沿用 12px；断点 1100px 以下回落单列 | 34/34 PASS，桌面 4 卡等宽等高（582×139），窄屏 1000px 单列（宽 770） |
| 页面显示「尚未产出，已立 BCI-002」是错的：新能源模板应立即产出 v1 并可选 | BCI-002 产出模板（8 组 43 维）+ `web/templates.json` 清单；本页模板下拉改为运行时读清单，选中写入 `bci.scope` | 39/39 PASS，新能源可选并写入 `insight_template=nev_user_insight`，新车型仍不可选 |

| # | 验收项 | 判定方式 |
|---|---|---|
| A1 | 导航一级入口可进入；4 个 tab 仅第 1 个可点 | 浏览器断言 |
| A2 | 四类各一个下拉，默认全部「不选」 | 断言四个下拉文案均为「不选」 |
| A3 | 定量三年可单选、可多选，未选年度不参与 | 勾选 2023+2025 后回显与写入值一致 |
| A4 | 定性只有 2025 可选；2026 不可选并给出原因 | 断言 2026 的 input 为 disabled 且含原因文案 |
| A5 | 新能源用户洞察模板可选，选中后写入 `insight_template=nev_user_insight`；新车型模板不可选，原因写明待业务提供 | 断言可选/不可选、localStorage 值与原因文案 |
| A6 | 流通数据不可选并说明「待业务提供」 | 断言 disabled + 原因 |
| A7 | 选择结果写入 `bci.scope`（含 `version` 与 `datasources`）；清空后移除并回到全部不选 | 读取 localStorage 断言 |
| A8 | 旧实现无残留：无车型可用性矩阵、chip、告警、下游参数契约块 | DOM 计数为 0 |
| A9 | 无 JS 运行时错误 | 捕获 `pageerror` / console error |
| A10 | 四类卡片桌面 2 列 × 2 行、等宽等高、行距 12px；窄屏（≤1100px）回落单列且卡片不被挤压 | 读取 4 张卡片 `getBoundingClientRect` 断言坐标、宽高与行距 |
| A11 | 模板列表不写死在前端，由 `/competitor-insight/templates.json` 提供 | 断言该请求 200；`bci.js` 内不含具体模板名与「待生成」文案 |
| A12 | 选源阶段只呈现四类下拉：无「本次分析口径」块、无「报告输出」占位，可见面板唯一 | DOM 计数 + 可见面板断言 |

## 4. 步骤与结果

| # | 步骤 | 状态 | 实际结果 |
|---|---|---|---|
| S1 | 登记用户驳回与口径纠正 | 完成 | 本文件第 2 节 |
| S2 | 核对三年定量源文件结构 | 完成 | 2023：959 份 / 851 题项；2024：2,094 份 / 1,042 题项；2025：1,380 份 / 1,324 题项（与库内 `quant_sample` 1380 一致） |
| S3 | 删除 5×5 服务与接口 | 完成 | 删除 `customer_insight/datasource_service.py`；移除 `app.py` 路由与 `do_POST` 白名单项 |
| S4 | 重做 tab ① 为四类选择器 | 完成 | 四类下拉、默认不选、不可选项带原因、口径预览与清空 |
| S5 | 前端资源迁入 `competitor_insight/web/` | 完成 | `bci.js`（自包含模块）、`bci.css`；`assets/home.js` 仅保留挂载，`assets/home.css` 不再含 BCI 样式；`app.py` 增 `/competitor-insight/` 静态路由与白名单 |
| S6 | 浏览器复验 | 完成 | 39/39 PASS，EXIT=0；勾选、单选、模板可选/新车型不可选、清单来源、口径写入与清空、桌面 2×2 / 窄屏单列布局全部通过。期间修复下拉浮层被分组动画层叠上下文覆盖的问题（`.bci-block` 动画填充由 `both` 改 `backwards`）；已知基线：`/api/health` 404 与本次无关 |
| S7 | 提交 git | 完成 | 随 `1bd7eee` 入库并推送；`commit_paths` 收窄见 `9cf1c03`，见 BCI-001-L06 |
| S8 | 用户验收 | 待做 | 见状态块 `next` |
| S9 | 越界修复（2026-11-09） | 完成 | 删除「本次分析口径」块与其 JSON 预览、删除 tab④「报告输出」占位；补 `.bci-panel[hidden]{display:none}`（`display:flex` 覆盖了 UA 的 `[hidden]`，导致未激活面板一并渲染）；断言 39→41 条，41/41 PASS |

## 5. 证据索引

- 当前有效证据：`outputs/competitor-insights/BCI-001/20261106-datasource-selector-r2/`
  - `verify_selector.py`：本轮浏览器验收脚本（可重跑）
  - `verify.log`：完整断言输出与退出码
  - `screenshots/bci-selector-open.png`、`bci-selector-selected.png`、`bci-layout-desktop.png`（桌面 2×2）、`bci-layout-narrow.png`（窄屏单列）
  - `manifest.json`：文件用途、来源、可重建性、保留策略
- **已作废证据**：`outputs/competitor-insights/BCI-001/20261106-datasource-tab/`（旧口径的 5×5 矩阵与 19 项断言，仅作历史追溯，不再代表当前实现）
- 只读探查脚本：`temp/20261106-bci/`（`probe_quant_xlsx.py`、`count_quant_rows.py` 等，可重建）

## 6. 已知边界（不是缺陷，但下游必须知道）

- 定量三年结构不一致：2023 只有 959 份、851 个题项；2024 为 2,094 份、1,042 个题项；2025 为 1,380 份、1,324 个题项。跨年合并前需先对齐题项。
- 只有 2025 年定量数据在库内（`quant_sample` 1,380 条）；2023/2024 目前只有源文件，未入库。
- 定性只有 2025 年解析结果（63 人）；2026 年音频尚未转写解析。
- 新能源用户洞察模板已有 v1（8 组 43 维，`competitor_insight/templates/`）；新车型模板仍待业务提供；流通数据也没有。模板列表来源为 `competitor_insight/web/templates.json`，新增模板不需要改前端 JS。

### 入库判定（commit_paths）的边界 — 2026-11-07 收窄

首次入库 `1bd7eee` 后，本任务的 `commit_paths` 从「竞品洞察文件 + 共享文件」收窄为**本任务独占的文件**，原因与后果如下，不删不藏：

| 路径 | 处理 | 原因 |
|---|---|---|
| `app.py` | **移出** | 共享文件。本任务的 3 处 hunk（`/competitor-insight/` 静态路由、`_send_file` 白名单变量与判定）已随 `1bd7eee` 入库；文件里仍有**深度调研任务**的未提交 hunk（imports、能力常量、skill 指令、validation/engine、`run_agent_once` 分支）与**智能问答任务**的 warning 文案改动 |
| `home.html` | **移出** | 共享文件。本任务的 4 处 hunk（bci.css 引用、导航项、视图骨架、bci.js 引用）已入库；文件残余为**首行 BOM 数量变化**（编辑器产物，非功能改动） |
| `docs/root-files.json` | **移出** | 项目级登记文件，非本任务独占；本任务新增的 `competitor_insight/` 一行已随 `1bd7eee` 入库，后续由其他任务继续追加 |

**手工登记（2026-11-09 越界修复）**：`home.html` 的 3 处 hunk（删除「本次分析口径」块、删除 tab④「报告输出」占位、引入 `bci-templates.css/js`）不在本任务 `commit_paths` 内，随 2026-11-09 越界修复提交入库；`app.py` 的模板只读路由属 BCI-002，本次未提交（文件内有其他任务在途 hunk）。今后再动这些共享文件仍需按此方式人工登记。

**盲区（已确认，必须知道）**：

- 文件级 `git status --porcelain` 无法区分同一文件内的 hunk 归属。把共享文件留在 `commit_paths` 里，会让别人的未提交改动持续把本任务判红；因此声明改为"本任务真正拥有的文件"。
- **代价**：`app.py`、`home.html`、`docs/root-files.json` 一旦被其他任务提交，`TASK-COMMITTED` 就**不再覆盖本任务在这三个文件上的后续改动**。今后本任务若再改这三个文件，必须在 TASK.md 人工登记改动与提交哈希，不能指望自动检查兜底。
- 收窄不是为了让看板变绿：判据是"这处改动是否由本任务独占"。若本任务再次独占某个共享文件（例如整文件都由竞品洞察改动构成），应把该路径加回。

## 7. 遗留问题

| 编号 | 问题 | 影响 | 现状 | 解除条件 | 负责人 | 证据/关联 |
|---|---|---|---|---|---|---|
| BCI-001-L01 | 新能源用户洞察模板未产出 | 该选项此前不可选 | **已关闭**（2026-11-06）：BCI-002 产出 v1（8 组 43 维），本页改为从 `templates.json` 读取并可选，39/39 PASS | 已完成 | TRAE | [BCI-002](BCI-002/TASK.md)、`outputs/competitor-insights/BCI-001/20261106-datasource-selector-r2/verify.log` |
| BCI-001-L02 | 新车型用户洞察模板缺失 | 该选项标记「待提供」 | 业务未提供 | 业务提供模板文件后登记可用性并改为可选 | 用户/业务 | 页面文案 |
| BCI-001-L03 | 2026 年定性深访音频未解析 | 2026 选项不可选 | 只有 2025 年 63 人 | 完成音频转写与解析入库，把该选项改为可选 | 业务/数据 | `interview` 表 |
| BCI-001-L04 | 2023/2024 定量数据未入库 | 选中后下游无表可查，只有源文件 | 仅附件 xlsx | 完成入库并验证题项对齐，再更新本页可用性说明 | TRAE/数据 | `quant_sample` |
| BCI-001-L05 | tab ①②③④ 未开发（① 洞察档案 = 勾选多人 → 43 维 rowspan 表 → 单人/多人导出，同样未做） | 选完口径没有消费方 | 仅骨架占位；**进展（2026-11-07）**：洞察档案已由 BCI-004、即时分析已由 BCI-006 交付，均 `TESTED` 待用户验收，本项剩余未开发 tab 另行立项 | 逐 tab 建任务并上线 | TRAE | 本任务 S4；核对见 BCI-002 `docs/template-vs-prototype-mapping.md` §7 |
| BCI-001-L06 | ~~改动未提交 git~~ 已解除 | — | **已关闭**（2026-11-07）：随 `1bd7eee` 入库并推送；声明收窄 `9cf1c03`，`check_board.py` 转 PASS | 已完成 | TRAE | `git log`、本文件 §6 |
| BCI-001-L07 | `bci.scope` 尚无后端消费方 | 多用户覆盖与刷新恢复未验证 | 仅前端写入 | 第二个 tab 落地后由真实读取方验证，并补刷新/多会话用例 | TRAE | `competitor_insight/web/bci.js` |
| BCI-001-L08 | `competitor_compare` 无车型集合入参 | 后续洞察对比可能跨全库；本 tab 不受影响 | 未修复 | 工具增加车型集合入参并用真实调用证明结果受约束 | TRAE | `customer_insight/tool.py` |

## 8. 阶段流转记录

| 日期 | 阶段 | 依据 | 证据 | 变更人 |
|---|---|---|---|---|
| 2026-11-06 | CREATED | 用户下达【数据源筛选】开发要求 | — | TRAE |
| 2026-11-06 | EXECUTING → TESTED | 首版实现（5 车 × 5 源可用性矩阵）完成并通过 19 项断言 | `outputs/.../20261106-datasource-tab/` | TRAE |
| 2026-11-06 | **退回 EXECUTING** | **用户驳回设计方向**：页面应为「四类数据源与模板的选择器」，不是车型可用性体检；原实现属自行扩展需求 | 本文件第 2 节 | 用户驳回 / TRAE 记录 |
| 2026-11-06 | EXECUTING | 删除 5×5 服务与接口，重做四类选择器，前端资源迁入 `competitor_insight/web/` | 第 4 节 S3–S5 | TRAE |
| 2026-11-06 | TESTED | 浏览器复验全部断言通过，退出码 0 | `outputs/.../20261106-datasource-selector-r2/verify.log` | TRAE |
| 2026-11-06 | TESTED → EXECUTING → TESTED | 用户验收反馈：四类卡片应为 2×2、窄屏单列；仅调布局，补 A10 后重跑 34 项断言通过 | 第 3 节用户反馈 + `verify.log` | 用户反馈 / TRAE |
| 2026-11-06 | TESTED → EXECUTING → TESTED | 用户验收反馈：新能源模板应可选（BCI-002 立即产出 v1）；模板下拉改为读 `templates.json`，补 A11、改 A5 后重跑 39 项断言通过 | 第 3 节用户反馈 + `verify.log` | 用户反馈 / TRAE |
| 2026-11-09 | TESTED → EXECUTING → TESTED | 用户对比原型指出选源阶段多渲染了「本次分析口径」「报告输出」两块；删除两块的 DOM 与样式，补 `[hidden]` 失效修复，断言 39→41 条全部通过 | `outputs/.../20261106-datasource-selector-r2/` | TRAE |
| — | LIVE | 待用户验收确认 | — | 待定 |

> 本任务的状态块建于任务制机制落地当天；首版工作此前以对话推进，本表按真实结果补记，不追溯改写历史。
