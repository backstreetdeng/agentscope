# BCI-003：学习 DeepSeek Harness 工程方法并评估对竞品洞察的适用性

```
task_id: BCI-003
title: 学习 DeepSeek Harness 工程方法并评估对竞品洞察的适用性
stage: TESTED
owner: TRAE
commit_paths: competitor_insight/docs/harness-study.md,competitor_insight/tasks/BCI-003,competitor_insight/tasks/tasks.md,competitor_insight/BOARD.md,competitor_insight/HANDOFF.md,outputs/competitor-insights/BCI-003
updated: 2026-11-09
blocked: no
next: 用户抽样复核三块决策记录（已采纳 4 / 已推翻 4 / 不立项 5）；纯文档无可访问入口，无 LIVE 动作，确认后关单
evidence: outputs/competitor-insights/BCI-003/20261109-decision-record/
```

## 1. 目标与边界

**目标**：真读三份材料（官方仓库、同事工程、用户给的文档），回答五个问题：Harness 核心机制、同事工程实际用法、对竞品洞察可落地的条目、不适用条目、最小第一步。

**边界**：

- 纯学习与评估，**不改任何业务代码**，不改 `web/`、`app.py`、`home.html`、`customer_insight/`。
- 不改现有任务机制（`RULES.md`、`check_board.py`、`tasks/_TEMPLATE`）——本轮结论只是建议，落地须另立任务并经用户确认。
- 不臆测 Harness 细节：取不到的标注"未取到"，没有实证的标注"未验证"。

**允许写入**：`competitor_insight/docs/harness-study.md`、本任务文件、`tasks/tasks.md`、`BOARD.md`、`HANDOFF.md`、`outputs/competitor-insights/BCI-003/`。

**范围变更（2026-11-06，用户指出）**：初版只读了同事工程的一个子项目 `projects/industry-tracking-v2/`，范围不足。完整项目目录为 `D:\colleague\炫琪\CATARC_业务组监测交接\02_工程\workspace`，本轮按整个 workspace 重扫，仍**只读、不改代码**。新增要求：结构地图、跨项目约定所在层级、单项目看不到的做法、对原 5 条建议的修正。产出方式为**在原文件追加"§5 全 workspace 复核"**，保留原结论并显式标注推翻/修正项，不另起平行文档。

**收敛（2026-11-09，用户确认方案）**：`docs/harness-study.md` 由"学习报告"降格为**决策记录**，只保留三块：① 已采纳（4 条，每条写采纳了什么 / 落在哪个约束文件与提交 / 现在拦得住什么）；② 已推翻（4 条，原结论 → 修正结论 + 日期与依据）；③ 不立项（5 条，逐条写为什么不值得做 + 什么条件下重议）。删除过程分析、五问、逐文件行号摘录与方法论铺陈；证据目录链接保留以便回溯。文档定位为"派单/改规则前查阅的决策记录"，状态真源仍是 `BOARD.md` 与各 `TASK.md`；不保留"由谁维护"的承诺。**本轮仍不改业务代码、不改任务机制规则。**

## 2. 验收标准

| # | 验收项 | 判定方式 | 证据要求 |
|---|---|---|---|
| A1 | 三份材料都有"读到了什么"的记录；未取到的明确说明尝试过程 | 对照 `docs/harness-study.md` §1 | 官方三份原文快照在证据目录；未取到项写进 §3 未验证清单 |
| A2 | 每条结论标注可信度：官方文档 / 代码实证 / 推断 | 全文检索三种标记 | `harness-study.md` 每节带标记 |
| A3 | 同事工程的结论全部带文件路径与行号 | 抽查 5 条与源文件比对 | 证据目录 `colleague-file-index.txt` 记录实际读取清单 |
| A4 | 五个问题都有直接答案，且不写成读书笔记 | 通读 §2 Q1–Q5 | 结论先行，Q3/Q4 用表格逐条给理由 |
| A5 | Q3 每条都写明落点文件与对应痛点编号 | 对照 `BOARD.md` 遗留挂账表 | Q3 表含"落在哪里""解决哪个痛点"两列 |
| A6 | Q5 给出可执行的改动量与不做什么 | 读 Q5 段落 | 写明新增文件、行数量级、不触碰范围 |
| A7 | 结构地图覆盖 workspace 各层，角色判定带路径/文件依据 | 读 §5.2 | 每层有"位置 + 角色 + 判定依据"；主工程/模板/历史项各有指名依据 |
| A8 | 跨项目约定标注所在层级（workspace / 项目 / 成对） | 读 §5.3 | 表格"层级""是否成对"两列 |
| A9 | 列出单项目看不到的做法，并逐条给出对原 5 条建议的修正 | 读 §5.4、§5.5、§5.6、§5.7 | 每条带证据文件与行号；明确标注推翻/修正/保留 |
| A10 | 收敛后只保留三块（已采纳 / 已推翻 / 不立项）与证据段，过程分析、五问、逐文件行号摘录已删除 | `check_decisions.py` 断言章节集合与已删除标题 | `20261109-decision-record/check.log` |
| A11 | 已采纳 4 条，每条含落点文件与提交号、并写明"现在拦得住什么" | 同上，逐行断言 | 同上 |
| A12 | 已推翻 4 条各带日期与依据；不立项 5 条各带"为什么不值得做"与"什么条件下重新考虑" | 同上，逐行断言 | 同上 |
| A13 | 文档写明定位（派单/改规则前查阅）与状态真源（BOARD.md + 各 TASK.md），且无"由谁维护"承诺 | 同上 | 同上 |

## 3. 步骤与结果

| # | 步骤 | 状态 | 实际结果 | 证据 |
|---|---|---|---|---|
| S1 | 建任务并登记三方 | 完成 | 本文件 + `tasks/tasks.md` + `BOARD.md` | `check_board.py` |
| S2 | 取官方 README 中文版 | 完成 | 内置抓取器返回空；改用 `Invoke-WebRequest` 取 raw 版 HTTP 200（2511 字符），另取 GitHub 页面版交叉核对 | `sources/deepseek-harness-README.zh.md` |
| S3 | 找同仓库规范/示例类文件 | 完成 | 根 `AGENTS.md`（19315 字符）、`docs/architecture.zh.md`（11326 字符）、`.agents/skills/` 24 个 skill 目录（仅列名） | 同上 + 证据目录两份 |
| S4 | 读同事工程的组织方式 | 完成 | 9 个文件：AGENTS/WORKFLOW/HARNESS/protocol.json/verify_harness.py/hard_gates.py/cost_gate.py/jobs.py/provenance.py | `colleague-file-index.txt` |
| S5 | 读用户给的两份文档并核对来源 | 完成 | 与同事工程 `docs/HARNESS.md`、`AGENTS.md` 逐字相同，判定为同一来源副本而非独立第三源 | `harness-study.md` §1.3 |
| S6 | 写学习与评估文档 | 完成 | `competitor_insight/docs/harness-study.md`（§0 结论 / §1 三源 / §2 五问 / §3 未验证 / §4 证据） | 该文件 |
| S7 | 跑一致性检查 | 完成 | `check_board.py` PASS；`workspace_hygiene.py` PASS | 见第 6 节 |
| S8 | 全 workspace 只读重扫（范围扩大后） | 完成 | 读到根 `AGENTS.md`(205 行)、`PROJECTS.md`(226)、`WORKSPACE-MIGRATION.md`(272)、`README.md`(87)、`.cursor/rules/00-workspace-hub.mdc`(16)、`.cursor/skills/industry-tracking-v2/SKILL.md`(38)、`policy-crawler/AGENTS.md`(112)、`policy-crawler/docs/HARNESS.md`(176)、`site-collect-cli/AGENTS.md`(57)、`site-collect-cli/config/status.v1.json`(89)，并核对 10 个在场项目统计 | `20261106-workspace-rescan/colleague-workspace-index.txt` |
| S9 | 更正上一版事实错误并追加 §5 | 完成 | 推翻"SKILL.md 不存在"；更正注册项目数 17→15（在场 10、缺失 5）；追加 §5.1–§5.8（结构地图、约定层级、7 条单项目盲区、5 条修正、新增 #6/#7、结论变化汇总） | `docs/harness-study.md` §5 |
| S10 | 按用户确认方案收敛文档 | 完成 | 重写为三块决策记录：已采纳 4 / 已推翻 4 / 不立项 5；删除五问、过程分析、逐文件行号摘录；保留三个证据目录链接；补定位与状态真源声明。**44 行 / 约 1472 字**（原 250 行） | `docs/harness-study.md` |
| S11 | 收敛结构校验 | 完成 | `check_decisions.py` 20 条断言 **20/20 PASS**；`check.log` 记录行数/字数 | `20261109-decision-record/` |
| S12 | 入账与三方同步 | 完成 | `tasks.md` / `BOARD.md` / `HANDOFF.md` 同批更新并随本任务提交推送；`check_board.py` 与 `workspace_hygiene.py` 结果见 `check.log` | `check.log`、`git log` |

## 4. 交付结论摘要

> 2026-11-09 收敛后，`docs/harness-study.md` 正文以三块决策记录为准（已采纳 4 / 已推翻 4 / 不立项 5）。以下为原评估结论摘要，仅作历史留痕，与正文冲突时以正文为准。

- 核心机制三层：无内核的插件挂载 + provider 可替换的能力 seam + 仅追加日志为唯一事实源，规范由 CI 门禁执行（`dsh ... --dump-config` 可打印实际插件树）。
- 同事工程实证最值得抄的四件（**§5.7 修正为五件**，见下一组条目）：真源分层（`AGENTS.md:15-27`）、人读文档与机器契约成对（`HARNESS.md:3` + `protocol.json:5-63`）、模型前确定性硬门且判定类 fail-closed（`hard_gates.py:288-294`）、隔离环境一键验收并按层给结论（`verify_harness.py:39-181`、`HARNESS.md:99-120`）。
- 可落地 5 条，最小第一步只做第 1 条：新增 `config/bci_protocol.json` + 让 `check_board.py` 校验"任务声称的落点是否真实存在"，约 1 个新文件 + 30~40 行只读检查。
- 不适用 5 条：插件树/profile 分层、逐文件 100% 覆盖率、subagent/team/todo 编排、会话日志迁移链、费用门闩（理由见 §2 Q4）。
- **全 workspace 复核修正（§5）**：同事搬走的是**五件**不是四件，漏掉的是"三层路由 + 贯通断言（文档开关→有代码读者→`verify` 绿灯、禁止装饰性 `true`）"。原 5 条建议中 2 条加强（#1 加 `reader`+`verify`、#3 加可抽检字段）、1 条修正（#2 验收列改为可机器读的 `open_items[]` 形态，不手抄看板）、1 条加强（#4 证据加 `pointers`）、1 条保留（#5 状态枚举）；新增 #6 任务级冻结清单/端口/owner、#7 任务模式 `read|change|publish` 决定验收强度；明确不采用 `agent-dod`。
- 结构地图要点：主工程 `policy-crawler`（28 篇 docs、双状态文件、被两处指定为成刊范例），模板 `projects/_template`（副本缺失），笔记/实验项 `auto-opinion-daily-layout-lab`、`h5-board`、`catarc-content`、`sales-forecast`。
- 副本完整性：注册 15 个项目、在场 10 个、缺 5 个（daily-work / ppt-auto / sales-forecast / catarc-engagement / auto-opinion-daily-layout-lab）与 `_template/`，缺失项相关判断一律未验证。

## 5. 证据索引

- 证据目录：`outputs/competitor-insights/BCI-003/20261106-harness-study/`
- `manifest.json`：产物清单与用途
- `sources/deepseek-harness-README.zh.md`、`sources/deepseek-harness-AGENTS.md`、`sources/deepseek-harness-architecture.zh.md`：官方原文快照（HTTP 200）
- `sources/colleague-file-index.txt`：同事工程实际读取清单与目录统计（其中「.cursor 不存在」一句已由下一目录更正）
- 全 workspace 复核证据目录：`outputs/competitor-insights/BCI-003/20261106-workspace-rescan/`
  - `colleague-workspace-index.txt`：10 个在场项目统计、15 注册/5 缺失、9:6 状态真源形态、`.cursor` 17 rules / 8 skills、14 个已读文件行数
  - `manifest.json`：范围、可复现命令、两处更正记录
- 无临时脚本；本轮只读统计使用内联 Python 命令，未落盘脚本。
- 收敛校验目录（2026-11-09）：`outputs/competitor-insights/BCI-003/20261109-decision-record/`
  - `check_decisions.py`：三块章节、条数、落点/提交、日期/依据、不立项理由与重议条件、已删除章节、证据目录存在，共 20 条断言
  - `check.log`：`20/20 PASS`，44 行 / 约 1472 字
  - `manifest.json`：产物与复现命令
- 注：状态块 `evidence` 按 `check_board.py` 规则只允许**单个**含 `manifest.json` 的目录，因此复核证据记在本节与 `20261106-workspace-rescan/manifest.json`，不写进状态块。

## 6. 已知边界（不是缺陷，但下游必须知道）

- 同事工程的 44 个离线测试**未在本机运行**（交接副本无虚拟环境，且不应在他人目录装依赖），因此"测试通过"只是其文档自述，不构成本次实证。
- ~~`.cursor/skills/industry-tracking-v2/SKILL.md` 在副本中不存在~~ → **已更正**：存在，在 workspace 根 `.cursor/skills/`（38 行）；初版误判是因为该指针相对 workspace 根而非项目目录。
- 交接副本不完整：注册 15 个项目、在场 10 个、缺 5 个与 `_template/`；缺失项目的规范与模板正文**未验证**，不据此下结论。
- 官方 23 个 `SKILL.md` 只读目录名、未读正文；`docs/testing.md`、`docs/defensive-patterns/` 未读。
- 同事其余 6 个 `SKILL.md` 与 16 个项目规则 `.mdc`（`.cursor/rules` 共 17 个，只读了 `00-workspace-hub.mdc`）正文未逐篇读，只确认存在与命名。
- Q3 第 5 条（空态区分"无数据/未覆盖"）的具体文案与 §5.6 新增 #6/#7 的字段设计是我的建议〔推断〕，不是来源中的既有做法。

## 7. 遗留问题

| 编号 | 问题 | 影响 | 现状 | 解除条件 | 负责人 | 证据/关联 |
|---|---|---|---|---|---|---|
| BCI-003-L01 | ~~本任务只是评估，Q3 五条均未落地~~ 已解除 | — | **已关闭**（2026-11-09）：原建议 #1/#5/#6 已由 BCI-005 落地（`1bd7eee`）；其余建议在决策记录第 3 节逐条**决定不立项**，不再挂账 | 已完成 | TRAE | `docs/harness-study.md` §1、§3 |
| BCI-003-L02 | 官方 23 个 `SKILL.md` 正文未读（同事 `.cursor/skills/industry-tracking-v2/SKILL.md` 已读，该半已关闭） | "技能机制是否同构"仍缺官方侧证据 | 只确认目录名与声明存在；**不影响三块决策记录的任何结论** | 需要时读官方 SKILL.md 正文补证；不阻塞任何任务 | TRAE | 决策记录 §2 第 1 条 |
| BCI-003-L03 | ~~新增文档与证据未提交 git~~ 已解除 | — | **已关闭**（2026-11-07）：`docs/harness-study.md` 与 `outputs/competitor-insights/BCI-003/` 随 `1bd7eee` 入库并推送 | 已完成 | TRAE | `git log`、第 5 节证据索引 |
| BCI-003-L04 | 交接副本缺 5 个项目与 `_template/`，模板规范正文无法核验 | §5.2 对"模板/骨架"的角色判定只依据三处指针，未见模板正文 | 已标注未验证 | 拿到完整交接包后补核 `_template/` | 用户 / TRAE | `20261106-workspace-rescan/colleague-workspace-index.txt` §3 |
| BCI-003-L05 | ~~§5.6 新增 #6/#7 与 §5.5 的字段设计尚未落地~~ 已解除 | — | **已关闭**（2026-11-09）：#6（owner/port/frozen_paths）随 BCI-005 落地（`1bd7eee`）；#7（`mode` 分类）在决策记录第 3 节第 4 条**决定不立项**并写明重议条件 | 已完成 | TRAE | `docs/harness-study.md` §1 第 2 条、§3 第 4 条 |

## 8. 阶段流转记录

| 日期 | 阶段 | 依据 | 证据 | 变更人 |
|---|---|---|---|---|
| 2026-11-06 | CREATED | 用户要求建 BCI-003，三源真读、回答五问、产出报告 | 本文件 | TRAE / 用户要求 |
| 2026-11-06 | CREATED → EXECUTING | 三源均已取到/读入，开始写评估 | 第 5 节证据 | TRAE |
| 2026-11-06 | EXECUTING → DEV_DONE | 文档成文、证据目录含官方原文快照与读取清单、`check_board.py` 与 `workspace_hygiene.py` 均 PASS | 第 5、6 节 | TRAE |
| 2026-11-06 | DEV_DONE（范围扩大） | 用户指出只读 `industry-tracking-v2` 一个子项目范围不足，改为全 workspace 只读复核；§5 追加完成，范围变更记入 §1 | 本文件 §1、§3 S8/S9；`20261106-workspace-rescan/` | TRAE / 用户要求 |
| 2026-11-06 | DEV_DONE（复核完成） | 两处事实错误已更正并在正文标注（SKILL.md 实际存在、注册项目 15 非 17）；5 条建议修正 + 新增 #6/#7 已成文 | `harness-study.md` §5.1、§5.5–§5.7 | TRAE |
| 2026-11-09 | DEV_DONE → TESTED | 用户确认方案：文档降格为三块决策记录并收敛完成；结构校验 `check_decisions.py` 20/20 PASS；`check_board.py` 与 `workspace_hygiene.py` 见 `check.log`；文档与证据同批提交并推送 | `20261109-decision-record/check.log`、`git log` | TRAE / 用户要求 |

> `LIVE` 不适用：本任务交付物是版本库内的决策记录，无用户可访问入口、无需重启服务；后续如需改为线上可查，另行立项。