# BCI-005：竞品洞察 · 任务机制 Harness 化（契约 reader/verify、三态计数、冻结路径）

```
task_id: BCI-005
title: 竞品洞察 · 任务机制 Harness 化（契约 reader/verify、三态计数、冻结路径）
stage: DEV_DONE
owner: TRAE
port: 7860
frozen_paths: competitor_insight/templates/nev_user_insight_template.json,competitor_insight/config/bci_protocol.json
commit_paths: competitor_insight/check_board.py,competitor_insight/config,competitor_insight/tasks/_TEMPLATE/TASK.md,competitor_insight/tasks/BCI-005,competitor_insight/tasks/tasks.md,competitor_insight/BOARD.md,competitor_insight/HANDOFF.md,competitor_insight/RULES.md,outputs/competitor-insights/BCI-005,temp/20261106-bci005
updated: 2026-11-06
blocked: no
next: 用户复核 TASK-COMMITTED 与反向验证记录；存量任务须先统一入库，本任务才能转 TESTED
evidence: outputs/competitor-insights/BCI-005/20261106-harness-adoption/
```

## 1. 目标与边界

**目标**：按 [harness-study.md](../../docs/harness-study.md) 的结论，只落地第 1、5、6 三条，把"文档写了但代码没读"的约束变成会被检查器拒收的机器契约：

1. **契约带 reader + verify**：`config/bci_protocol.json` 每条约束含 `id / statement / reader / verify`；`check_board.py` 校验 reader 指向的符号真实存在、verify 命令真执行且返回 0。
2. **三态 + 计数**：检查脚本输出统一带 `status: success|partial|failed` 与「应查 / 实查 / 命中」；`partial` 必须列未覆盖原因，不得渲染成 0 条。
3. **任务级隔离**：TASK 模板增加 `owner / port / frozen_paths`；`check_board.py` 对声明了冻结路径的任务做越界检查，并检测非终态任务的端口冲突。

**追加（用户 2026-11-06 硬原则，不新增任务编号）**：任务必须入库才能算完成——`TESTED` 前本地提交、`LIVE` 前推送远程；落地为第 5 条约束 `TASK-COMMITTED`，见 §3 S11。

**本轮边界**：

- **不碰业务代码**：不改 `app.py`、`home.html`、`web/bci.js`、`web/bci.css`、`web/templates.json`、`templates/*`；不重启 7860、不建表、不查库。
- 只改任务机制文件：`check_board.py`、新增 `config/`、`tasks/_TEMPLATE/TASK.md`、任务文档与证据。
- 第 2、3、4、7 条建议（验收列、纯函数门禁、证据 TRACE、模式分类）本轮**不做**。
- 不改 `nev_user_insight_template.json` 一个字节（已声明为冻结路径并由基线保护）。

**允许写入**：`competitor_insight/check_board.py`、`competitor_insight/config/**`、`competitor_insight/tasks/_TEMPLATE/TASK.md`、`competitor_insight/tasks/BCI-005/**`、`tasks/tasks.md`、`BOARD.md`、`HANDOFF.md`、`RULES.md`（字段说明）、`outputs/competitor-insights/BCI-005/**`。

## 2. 验收标准（必须可判定）

| # | 验收项 | 判定方式 | 证据要求 |
|---|---|---|---|
| A1 | 协议文件含 5 条约束，字段齐全，reader 指向真实符号 | 读 `config/bci_protocol.json`；`check_board.py` 逐条校验 | 检查器输出 counts 命中 0 |
| A2 | 每条 verify 都是真断言，被破坏时确实 FAIL | 4 条各做一次「破坏副本 → 应 failed → 恢复 → success」 | `reverse-verify.log` 逐条记录 |
| A3 | reader 符号不存在时判 FAIL | 破坏 reader 指向（临时副本）→ 应 failed | `reverse-verify.log` |
| A4 | 敷衍 verify（`echo ok` / `exit 0` / `-c pass`）被识别 | 临时协议里放一条敷衍 verify → 应 failed | `reverse-verify.log` |
| A5 | 输出带三态与计数，partial 不渲染 0 条 | 运行检查器看 `status` / `counts` / 未覆盖段 | `verify.log` |
| A6 | 存量 BCI-001~004 不受新字段影响 | 运行 `check_board.py` 全部 PASS | `verify.log` |
| A7 | TASK 模板含 owner/port/frozen_paths 且有用法说明 | 读 `tasks/_TEMPLATE/TASK.md` | 文件本身 |
| A8 | 冻结路径被改动时 FAIL，恢复后 PASS | 改 `bci_protocol.json` 一个字节 → failed → 还原 → success | `reverse-verify.log` |
| A9 | 端口非法/冲突可被发现 | 临时把 port 改成非整数 → failed；临时副本制造同端口 → 命中冲突 | `reverse-verify.log` |
| A10 | 无业务代码改动 | `git status` + 冻结基线 | `git-status.txt` |
| A11 | 目录卫生通过 | `scripts/workspace_hygiene.py` | `verify.log` |
| A12 | `TASK-COMMITTED` 能检出未入库：声明文件集有未提交或未跟踪改动即 FAIL，提交后 PASS；留空 `commit_paths` 不能绕过；`LIVE` 无上游判 FAIL | 临时 git 仓库 6 个用例（干净→PASS、已跟踪未提交→FAIL、未跟踪→FAIL、提交后→PASS、LIVE 无上游→FAIL、未声明→FAIL） | `reverse-verify-committed.log` |

## 3. 步骤与结果

| # | 步骤 | 状态 | 实际结果 | 证据 |
|---|---|---|---|---|
| S1 | 新增 `config/verify/verify_constraints.py`（只读断言脚本，三态输出） | 完成 | 4 个子检查 TPL-SOURCE / TPL-READY / SCOPE-PERSIST / SCOPE-KEYS，单独运行均 success（应查 16/18/8/7） | `config/verify/verify_constraints.py` |
| S2 | 新增 `config/bci_protocol.json` | 完成 | 现有 5 条约束，均含 id/statement/reader/verify，reader 指向真实函数 | 文件本身 |
| S3 | 改 `check_board.py`：协议校验（reader 符号 + verify 执行）、敷衍项拦截、递归拦截 | 完成 | 新增 `check_protocol()`、`run_verify()`、`normalize_reader()` | `check_board.py` |
| S4 | 改 `check_board.py`：三态与计数 | 完成 | `Tally` 统一计数，输出 `status` / `counts` / 未覆盖段；partial 不显示成 0 命中 | `check_board.py` |
| S5 | 改 `check_board.py`：frozen_paths 与 port | 完成 | 已跟踪文件比 `git status --porcelain`，未跟踪文件比 sha256 基线；`--freeze` 写基线；port 校验整数 + 非终态冲突 | `check_board.py` |
| S6 | TASK 模板加字段 | 完成 | 增加 `port: none`、`frozen_paths: none` 与两行用法说明 | `tasks/_TEMPLATE/TASK.md` |
| S7 | 兼容存量任务 | 完成 | 未声明 port/frozen_paths 视为不限制；BCI-001~004 运行后仍 success（应查 137 / 命中 0） | `verify.log` |
| S8 | 为 BCI-005 建立冻结基线 | 完成 | `--freeze BCI-005` 写入两条 sha256（档案模板 + 协议文件） | `tasks/BCI-005/frozen.sha256` |
| S9 | 反向验证（逐条破坏→FAIL→恢复→PASS） | 完成 | 4 条 verify + reader 缺失 + 敷衍 verify + 冻结越界 + port 非法/冲突，全部按预期失败 | `reverse-verify.log` |
| S10 | 同步 RULES / tasks.md / BOARD / HANDOFF | 完成 | 字段说明与登记行落地 | 见第 4 节 |
| S11 | 追加 `TASK-COMMITTED`（用户硬原则：TESTED 前本地提交、LIVE 前推送） | 完成 | `bci_protocol.json` 增第 5 条；`verify_constraints.py` 增 `check_task_committed()`；`RULES.md` §6/§12 写入硬规则；5 个 TASK.md 补 `commit_paths`；临时 git 仓库 6/6 用例符合预期；真实仓库当前 `status: failed`（BCI-001 7 处、BCI-002 6 处未入库） | `reverse-verify-committed.log`、`verify.log` |

## 4. 证据索引

- 证据目录：`outputs/competitor-insights/BCI-005/20261106-harness-adoption/`
- `manifest.json`：产物、范围、复现命令
- `verify.log`：正常路径运行结果（五条约束 + check_board + 卫生检查）；含 `TASK-COMMITTED` 当前的 failed 明细
- `reverse-verify.log`：逐条破坏与恢复的完整记录（含退出码与关键输出）
- `reverse-verify-committed.log`：`TASK-COMMITTED` 在临时 git 仓库上的 6 个反向用例
- `git-status.txt`：改动文件清单与冻结基线
- 临时脚本放 `temp/20261106-bci005/`（`reverse_verify.py`、`reverse_committed.py`），不落证据目录；反向验证使用临时目录，完成后删除。

## 5. 已知边界（不是缺陷，但下游必须知道）

- **reader 检查是词法匹配**（`\b符号\b`），不是 AST 或调用图：同名符号出现在别处会被误判为"有读者"。它拦得住"符号根本不存在"，拦不住"存在但没被调用"。
- **frozen 对未跟踪文件用 sha256 基线**：因为 `competitor_insight/` 整体未纳入 Git，`git diff` 对它是空的；基线文件被删会判 FAIL，不会静默放行。文件纳入 Git 后自动改用 `git status --porcelain`。
- **端口冲突只比对非终态任务**（CREATED / EXECUTING / QA）：DEV_DONE / TESTED 的历史任务不与新任务互斥。
- **三态只落在检查脚本**：`app.py` 与 `bci.js` 的返回值仍是原样，业务接口三态属后续任务（见 L01）。
- verify 会执行本地命令（当前 5 条，秒级、不联网）；180s 超时视为失败。
- **`TASK-COMMITTED` 只对 `TESTED`/`LIVE` 生效**：`CREATED`/`EXECUTING`/`DEV_DONE`/`QA` 允许存在未提交改动，否则任务根本无法开工。
- **判定依据是文件级 `git status --porcelain`**：能发现「工作区有未提交改动」「新增文件未跟踪」「改了没提交」；不能发现「已提交但提交内容不对」「提交在别的分支」「远程仓库实际不可回滚」。`LIVE` 用 `git rev-list --count @{u}..HEAD` 判断是否已推送，无上游一律判 FAIL（宁严不松）。
- **`commit_paths` 由任务自己声明**：声明范围过窄会漏判（只写了一个目录，实际改了范围外文件），这是本机制的已知盲区；当前靠人工在 TASK.md 写全，后续可改为按 diff 推断。
- `competitor_insight/` 整体尚未纳入 Git，因此当前所有任务都会被判「未入库」——这是真实状态，不是检查器误报。

## 6. 遗留问题

| 编号 | 问题 | 影响 | 解除条件 | 负责人 |
|---|---|---|---|---|
| BCI-005-L01 | 业务接口未带三态与计数 | 页面仍可能把"未覆盖"显示成 0 条 | 在 BCI-004 后端查询层落地时统一加 `status` + counts | TRAE |
| BCI-005-L02 | reader 仅为词法存在性检查 | 无法证明调用关系 | 需要时引入 AST/调用图检查 | TRAE |
| BCI-005-L03 | 冻结基线是本地文件，未纳入 Git | 换机器需重新 `--freeze` | 用户授权提交后一并入库 | 用户 / TRAE |
| BCI-005-L04 | 改动未提交 Git | 成果只在工作区，无法回滚 | 用户授权后按文件粒度提交 | 用户 |
| BCI-005-L05 | 存量任务全部未入库：BCI-001/002（`TESTED`）各 7/6 处未提交，BCI-003/004/005（`DEV_DONE`）整体未跟踪；`check_board.py` 当前如实 `status: failed` | 看板为红；BCI-001/002 不得视为完成，不得转 `LIVE` | 用户计划在 BCI-004 完成后统一提交（本地提交 + 推送远程）；提交后 `TASK-COMMITTED` 应转 PASS，届时把本 TASK 与 BOARD「入库状态」同步为已入库 | 用户 / TRAE |
| BCI-005-L06 | `commit_paths` 由任务人工声明，声明不全即漏判 | 机制可被"少写路径"绕过 | 改为按实际 diff 推断或强制覆盖 `competitor_insight/` 全量 | TRAE |

## 7. 阶段流转

| 日期 | 从 → 到 | 依据 | 证据 | 操作人 |
|---|---|---|---|---|
| 2026-11-06 | 创建 → EXECUTING | 用户批准第 1、5、6 条落地 | 本文件 | TRAE |
| 2026-11-06 | EXECUTING → DEV_DONE | 三条实现完成；反向验证逐条通过；BCI-001~004 仍 PASS；卫生检查 PASS | `verify.log`、`reverse-verify.log` | TRAE |
| 2026-11-06 | DEV_DONE（补范围，未改阶段） | 用户追加硬原则「任务必须入库」：新增 `TASK-COMMITTED`，RULES §6/§12 与 5 个 TASK.md 的 `commit_paths` 落地；临时仓库 6/6 反向用例通过；真实仓库因存量未入库如实转红 | `reverse-verify-committed.log`、`verify.log` | TRAE |
| — | DEV_DONE → TESTED | 用户复核机制输出并确认，且存量任务完成统一入库 | — | 待定 |
