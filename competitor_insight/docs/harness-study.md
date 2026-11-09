# 竞品洞察 · Harness 方法决策记录

> **定位**：派单、改 `RULES.md`、改 `check_board.py` 或新增任务约束**之前**查阅的决策记录。只回答三件事：哪些做法已经落地、哪些当初判断错了、哪些决定不做。
> **状态真源**：`competitor_insight/BOARD.md` 与各 `tasks/BCI-NNN/TASK.md`。本文件不记录任务进度、不替代看板，也不承诺由谁维护——规则与代码变了就回来改对应条目。
> **来源**：2026-11-06 对 DeepSeek Harness 官方仓库与同事 workspace 的只读学习，原始证据见文末「证据」。

## 1. 已采纳（4 条，均已落地）

| # | 采纳了什么 | 落在哪个约束 / 文件 / 提交 | 现在拦得住什么 |
|---|---|---|---|
| 1 | **约束必须带 `reader` + `verify`**：文档写下的每条约束都要指明哪份代码在读它、用什么命令能自动验证；`verify` 必须是真断言 | `config/bci_protocol.json`（5 条约束）→ `check_board.py` 的 `check_protocol()` / `run_verify()` → `config/verify/verify_constraints.py`；提交 `1bd7eee` | reader 指向的符号不存在 → FAIL；verify 写成 `echo ok` / `exit 0` / `-c pass` 被识别为敷衍 → FAIL；verify 退出码非 0 → FAIL |
| 2 | **任务级隔离字段**：`owner` / `port` / `frozen_paths` 写进状态块，冻结路径先建基线 | `RULES.md` §5、`tasks/_TEMPLATE/TASK.md`、`check_board.py` 的 `--freeze` 与端口冲突检查；提交 `1bd7eee` | 冻结文件被改动（已跟踪比 `git status`、未跟踪比 sha256 基线）→ FAIL；两个非终态任务声明同一端口 → FAIL |
| 3 | **检查输出带三态与计数**：`status: success\|partial\|failed` + 「应查 / 实查 / 命中」，partial 必须列未覆盖原因 | `check_board.py` 的 `Tally`、`config/verify/verify_constraints.py`；提交 `1bd7eee` | 把「未覆盖」写成「0 条命中」这种静默放行；partial 必须交代漏了什么 |
| 4 | **入库是阶段硬条件**（用户 2026-11-06 追加，非原建议）：`TASK-COMMITTED` 约束 | `bci_protocol.json` 第 5 条、`verify_constraints.py:check_task_committed`、`RULES.md` §6；提交 `1bd7eee` | `TESTED`/`LIVE` 任务的 `commit_paths` 内有未提交或未跟踪文件 → FAIL；`LIVE` 未推送远程 → FAIL；`commit_paths` 留空不能绕过 |

已知边界（不是缺陷）：`reader` 是词法存在性匹配，拦不住「符号存在但没被调用」（BCI-005-L02）；`TASK-COMMITTED` 是文件级判定，区分不了同一共享文件内不同任务的 hunk，且 `commit_paths` 声明过窄仍可绕过（BCI-005-L06）。

## 2. 已推翻（4 条）

| # | 原结论（2026-11-06 初版） | 修正后的结论 | 日期 / 依据 |
|---|---|---|---|
| 1 | `.cursor/skills/industry-tracking-v2/SKILL.md` 在交接副本中不存在，同事的技能包组织方式无实证 | **存在**，位于 workspace 根 `.cursor/skills/`（38 行）；项目 `AGENTS.md:44-45` 的指针是相对 workspace 根 | 2026-11-06 复核；`20261106-workspace-rescan/colleague-workspace-index.txt` |
| 2 | 同事工程从 Harness 搬走了「四件」（真源分层、机器契约、确定性硬门、隔离验收） | **五件**：漏掉最重要的一件「贯通断言」——文档开关 → 必须有代码读者 → `verify` 绿灯，禁止装饰性 `true`。这正是第 1 节第 1 条落地的来由 | 2026-11-06 复核；`policy-crawler/docs/HARNESS.md:30` |
| 3 | 同事 workspace 注册项目 17 个（误把 `.cursor/rules/` 下 17 个 `.mdc` 当项目数） | 注册 **15** 个、在场 **10** 个、缺失 **5** 个与 `_template/`；缺失项目相关判断一律未验证 | 2026-11-06 复核；`PROJECTS.md:14-28` |
| 4 | 建议 #2「验收表加一列『验证层级』，禁止把接口 200 写成功能验收」是首选小改动 | 手写列要与 `tasks.md`/`BOARD.md` 双写，必然漂移；真要区分层级应做成机器可读字段。结论：该建议**不立项**（见第 3 节第 1 条），验收层级继续写在 TASK.md「判定方式 / 证据要求」两列 | 2026-11-06 复核；`status.v1.json:38-79`（同事用 `open_items[]` 而非手写列） |

## 3. 不立项（5 条，逐条写明理由，避免重复提出）

| # | 建议 | 为什么不值得做 | 什么条件下重新考虑 |
|---|---|---|---|
| 1 | 验收表加「验证层级」列（原 #2） | 见第 2 节第 4 条：列是给人看的，会和看板双写漂移；现有 TASK.md 的「判定方式 / 证据要求」+ 证据目录已能区分「选项能点」与「功能可用」 | 出现「接口 200 被写成功能验收」的真实事故，且现有两列没拦住 |
| 2 | 口径判定写成纯函数 + 单测（新增 `server/gates.py`，原 #3） | 判定对象（tab ②③④ 查询层）尚未全部有消费方；先写校验器就是「接口加了没人用」，正是本次学习批评的反面案例 | 档案写入或查询校验真正落库时，按模板 `dimensions` 写必填/类型校验（对应 BCI-002-L02） |
| 3 | 证据 `manifest.json` 增加 TRACE / `pointers` 段（原 #4） | 关键结论已在 TASK.md 与 manifest 的 `purpose`/`reproduce`/`files` 里；再加一段没有脚本会读，属于装饰性字段 | 出现「换人接手必须问人才能复现」的实际案例 |
| 4 | TASK 状态块加 `mode: read\|change\|publish` 决定验收强度（原 #7） | 只省掉「纯文档任务为什么没有测试」的解释成本，却要每任务多填一个无法自动判定的字段；`RULES.md` §6 已允许显式列出未测项与原因 | 纯只读/纯文档任务占比过半，或出现借 read 模式绕过测试的案例 |
| 5 | 浏览器验收改成录制/回放快照（原「可选」条） | 前提是先有稳定接口层；现在绑在 DOM 上，前端一改回放全废，维护成本高于重跑一次 Playwright | tab 全部落地、DOM 稳定，且验收脚本单次耗时成为瓶颈 |

整类不适用（一次性记录，不再逐条讨论）：一切皆插件的 profile/bundle/patch 分层、逐文件 100% 覆盖率门禁、subagent/team/todo 会话编排、仅追加会话日志 + 版本迁移链、费用门闩。理由一致：竞品洞察是单入口短链路（选口径 → 查询 → 展示），这些机制的成本高于收益。

## 证据

- 官方三份原文快照与读取清单：[20261106-harness-study](file:///E:/AI/data/envs/helloagent/myproject/outputs/competitor-insights/BCI-003/20261106-harness-study/)（`sources/`、`manifest.json`）
- 全 workspace 只读复核：[20261106-workspace-rescan](file:///E:/AI/data/envs/helloagent/myproject/outputs/competitor-insights/BCI-003/20261106-workspace-rescan/)（`colleague-workspace-index.txt`、`manifest.json`）
- 落地实现与反向验证：[BCI-005 证据](file:///E:/AI/data/envs/helloagent/myproject/outputs/competitor-insights/BCI-005/20261106-harness-adoption/)（`verify.log`、`reverse-verify.log`）
- 本次收敛的结构校验：[20261109-decision-record](file:///E:/AI/data/envs/helloagent/myproject/outputs/competitor-insights/BCI-003/20261109-decision-record/)（`check_decisions.py`、`check.log`）
