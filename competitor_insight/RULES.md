# 竞品洞察开发规范 · 任务制 V1.1

- 生效：2026-11-06（Asia/Shanghai）
- 适用范围：`myproject/competitor_insight/` 及其产出的后端服务、接口、页面、数据口径与下游 tab。
- 上位规则：项目根 [AGENTS.md](../AGENTS.md)、[.trae/rules/trae-collaboration.md](../.trae/rules/trae-collaboration.md) 优先。本文件只细化竞品洞察这条线，不复制、不替代全项目规则。

## 1. 目录与唯一状态源

```
competitor_insight/
├── README.md                    入口与导航
├── RULES.md                     本规范
├── BOARD.md                     全局看板（按阶段分栏）
├── HANDOFF.md                   最近一次交接摘要
├── check_board.py               只读一致性检查（tasks.md ↔ BOARD ↔ TASK）
├── web/                         竞品洞察专属前端资源（由 app.py 的 /competitor-insight/ 路由提供）
│   ├── bci.js                   ① 数据源筛选模块
│   └── bci.css                  ① 的样式
├── server/                      竞品洞察专属后端实现（有代码时才建；路由注册仍在 app.py）
└── tasks/
    ├── tasks.md                 任务总表：编号、标题、阶段、负责人、更新时间、下一步
    ├── _TEMPLATE/TASK.md        新任务模板
    └── BCI-NNN/TASK.md          任务的唯一状态文件
```

- **一个任务只有一个状态文件**：`tasks/<任务编号>/TASK.md`。
- **一份总表**：`tasks/tasks.md` 汇总所有任务的编号/标题/阶段/负责人/更新时间/下一步。
- 三方必须一致：`tasks/tasks.md` ↔ `BOARD.md` ↔ 各 `TASK.md`。冲突时以 `TASK.md` 为准，并同时回改总表与看板；`check_board.py` 不通过即视为阶段未完成。
- 任务目录内只放文本类材料（决策记录、评审意见、契约草案、模板稿件）。截图、日志、报告、测试输出等大体积证据放 `outputs/competitor-insights/<任务编号>/<run-id>/`，TASK.md 只写链接。
- 不为同一条工作另建目录或第二个清单；遗留项挂在所属任务上，不散落。

## 2. 代码落点（硬约束）

- 竞品洞察专属的代码一律在本目录内创建、编辑、删除：
  - 前端：`competitor_insight/web/`，由 `home.html` 引用、经 `/competitor-insight/` 路由提供；不再写进 `assets/home.js`、`assets/home.css`。
  - 后端：`competitor_insight/server/`，`app.py` 只做路由注册与请求/响应装配，具体实现从这里 import。
- 共用底座**留在原位**，只通过 import 引用，不复制、不搬迁：`customer_insight/quant_service.py`、`customer_insight/retrieval_service.py`、`customer_insight/insight_service.py`、`customer_insight/segment_aliases.py` 及 `customer_insight/tool.py` 等智能问答链路依赖的模块。
- 判断标准：只服务竞品洞察的 → 进本目录；被问答与竞品洞察共用的 → 留原位。拿不准时按"是否被其他链路 import"实测后决定，并在任务中写明依据。
- 页面骨架（`home.html` 的视图结构与导航）属于全站入口，允许在 `home.html` 内维护，但其中的样式与脚本必须来自 `competitor_insight/web/`。

## 3. 什么必须落任务

必须先建/接入任务才能动手：

1. 新增或改动竞品洞察链路的代码、接口、页面、样式与交互。
2. 数据源接入、口径调整、车型命名映射、样本量与可用性判定规则的任何变更。
3. 缺陷修复、线上问题排查；同一问题需要多轮处理的，必须立任务。
4. 质量验证、补测、上线与回滚。
5. 需要改动共享文件的工作（`app.py`、`home.html`、`customer_insight/*` 等）。
6. 需要他人或后续接续的工作，包括"本轮先不做"的结论。

不必建任务：纯只读咨询、解释既有实现、单条查询、临时数据探查（脚本放 `temp/<YYYYMMDD>-<slug>/` 并说明用途）。

**成果物必须落成文件**：结论、口径、验收结果、证据路径写进 TASK.md 或证据目录；只存在于对话里的内容不算交付。

## 4. 任务编号与目录

- 前缀固定 `BCI`，三位递增：`BCI-001`、`BCI-002`……编号不复用、不改号、不改名已存在目录。
- 编号与代码里的 `/api/bci/*` 命名空间保持一致，便于从接口反查任务。
- 一个任务对应一条可独立验收的交付。范围过大拆成多个任务，但**不得用拆号绕过未完成项**；任务未完成也不得另开同范围新任务。
- 新建编号或目录需用户明确确认；同一任务内追加阶段、步骤、遗留项不需要确认。
- 目录名只放编号：`tasks/BCI-001/`；标题写在 TASK.md 状态块与 `tasks.md` 总表。

## 5. 状态字段（TASK.md 顶部固定块）

TASK.md 第一个代码块必须是状态块，字段如下（`check_board.py` 按此解析）：

| 字段 | 含义 | 取值/格式 |
|---|---|---|
| `task_id` | 任务编号 | `BCI-NNN`，必须与目录名一致 |
| `title` | 一句话任务名 | 中文短标题 |
| `stage` | 当前阶段 | `CREATED` / `EXECUTING` / `DEV_DONE` / `QA` / `TESTED` / `LIVE` |
| `owner` | 当前执行者 | `TRAE` / `Codex` / 用户名 |
| `port` | 本任务占用的端口（可选） | 整数；不占用写 `none`。两个非终态任务（CREATED/EXECUTING/QA）不得声明同一端口 |
| `frozen_paths` | 本任务禁止改动的文件（可选） | 逗号分隔的相对路径；不限制写 `none`。声明后先运行 `check_board.py --freeze BCI-NNN` 建立 sha256 基线 |
| `commit_paths` | 本任务的文件集，用于入库判定（可选，`TESTED`/`LIVE` 时必填） | 逗号分隔的相对路径（可含目录）；建议包含 `tasks/<编号>`、交付文件与 `outputs/competitor-insights/<编号>` |
| `updated` | 最后更新时间 | `YYYY-MM-DD` |
| `blocked` | 是否阻塞 | `yes` / `no` |
| `blocker` | 阻塞原因 | `blocked: yes` 时必填：现象 + 已试过的替代方案 + 解除条件/人 |
| `next` | 下一步动作 | 一句话，必须可执行 |
| `evidence` | 当前阶段证据目录 | `outputs/competitor-insights/<编号>/<run-id>/`；尚无证据写 `none` |

`tasks/tasks.md` 与 `BOARD.md` 中的阶段、负责人、更新时间、下一步必须与上表逐项一致。

`port` 与 `frozen_paths` 为可选字段：存量任务未写时按「未声明 = 不限制」处理，不因此判 FAIL；任务重新进入 EXECUTING 时应补写。

## 6. 阶段与准入条件

阶段链：创建 → 执行中 → 开发完成（待验证）→ 质量验证 → 测试通过（待上线）→ 已上线。「阻塞」不是阶段，是任一阶段上的显式标记。

| # | 阶段 | 代码 | 进入条件（缺一不可） |
|---|---|---|---|
| 1 | 创建 | `CREATED` | 目标与边界、可判定的验收标准、证据目录位置、涉及文件/模块、禁止范围已写入 TASK.md；需改动共享文件时写明影响面 |
| 2 | 执行中 | `EXECUTING` | 步骤已拆成可执行条目并标待做；已核对 Git 状态、不覆盖他人改动 |
| 3 | 开发完成（待验证） | `DEV_DONE` | 每个步骤标注"完成/未做/阻塞"并写实际结果（不是计划）；列出新增与修改文件；写明 git 状态；有 `git status`/`diff --stat` 或等价证据 |
| 4 | 质量验证 | `QA` | 至少一个可复现的验证入口（脚本或命令 + 运行方式）已放入证据目录；证据目录有 `manifest.json`；不得只写"已验证" |
| 5 | 测试通过（待上线） | `TESTED` | 测试命令、退出码、通过/失败计数、失败明细、既有基线失败单列、未测项显式列出；日志文件在证据目录；浏览器验收需附截图与断言清单 |
| 6 | 已上线 | `LIVE` | 改动已在用户可访问入口生效（URL + 菜单路径），附实际访问证据；如需重启服务，记录重启时间与影响；遗留项已挂账；用户验收或明确授权上线 |

- 不允许执行者从 `DEV_DONE`/`QA` 直接跳到 `LIVE`。
- **入库是阶段准入的硬条件（用户 2026-11-06 明确）**：任务到达 `TESTED` 之前必须在本地提交（相关文件集无未提交/未跟踪改动），到达 `LIVE` 之前必须已推送远程。**未入库的任务不得标为完成**；`check_board.py` 的 `TASK-COMMITTED` 约束会对处于 `TESTED`/`LIVE` 的任务按其声明的 `commit_paths` 做 `git status --porcelain` 判定，未入库即 FAIL。
- "自测通过"不等于"质量验证通过"：后者要求第三方能按同样命令复现。
- 阶段回退允许且必须留痕：谁、何时、依据什么驳回，写在 TASK.md 的「阶段流转记录」。

## 7. 谁能改状态

- **同一时间只有一个写入方**（项目规则）。当前执行者维护 TASK.md 的 `stage`/`blocked`/`next`/步骤/证据，以及 `tasks/tasks.md`、BOARD.md、HANDOFF.md。
- 只读方（接班前、旁观、其他 AI）**不得**改状态。发现问题时在 TASK.md 追加"外部发现"条目或记录到 HANDOFF，由写入方决定是否变更阶段。
- 用户可直接要求改状态或驳回。用户驳回时，执行者把阶段回退并写明驳回依据。
- 交接期间：交班方停止写入并在 HANDOFF 记最后状态；接班方读 TASK.md 与代码后成为新写入方，不重复已完成步骤。

## 8. 证据规范

- 目录：`outputs/competitor-insights/<任务编号>/<run-id>/`，`run-id` 用 `YYYYMMDD-短描述`。**同一 run-id 不覆盖**；重跑新开 run-id，旧目录保留。
- 每次运行必带 `manifest.json`，字段按 [docs/artifact-manifest-template.json](../docs/artifact-manifest-template.json)。同目录存放脚本、日志、截图、报告。
- 证据必须能回答：用了什么命令、什么输入、什么时间、退出码、结果数字、失败项、环境与已知限制。
- 只读探查脚本放 `temp/<YYYYMMDD>-<slug>/` 并在任务中写路径；可复用的验收脚本随证据目录保留。
- 不写凭据、不贴业务数据正文、不把未运行的测试写成通过、不把接口 200 当成功能验收。

## 9. 交接写法

在 HANDOFF.md **顶部追加**一条（新的在上），必须包含六项：

1. 当前任务编号与阶段；
2. 已改文件清单与 git 状态（已提交/未提交/未跟踪）；
3. 已运行测试与结果（含未跑项）；
4. 未解决问题（引用 TASK.md 遗留编号）；
5. 下一步与负责人；
6. 最后更新时间。

- TASK.md 的 `next` 必须与 HANDOFF 第一条一致；不一致以 TASK.md 为准并修正 HANDOFF。
- 交接只写事实，不写"应已完成"。突发中断时 HANDOFF 可能滞后，接班方以 TASK.md + 实际 Git/代码为准。
- 不在任务记录中写入密钥、会话凭据或浏览器 Cookie。

## 10. 遗留问题挂账

- 统一登记在所属 TASK.md 的「遗留问题」表，编号 `<任务编号>-L01` 起递增。
- 每条必填：编号、问题、影响、现状、**解除条件**、负责人、关联证据/任务。
- 只有"待改进""后续优化"没有解除条件的，视为不合格条目。
- BOARD.md 维护「全局限留挂账」聚合表，只列未关闭项；关闭时在 TASK.md 标「已关闭 + 证据」，再从看板移除。
- 属于其他任务的遗留挂到对应任务并互相链接，不复述两份。
- 用户明确决定不做的项目标「已决定不做」并记录决定人与日期，不计入遗留。

## 11. 阻塞处理

- 任一阶段可置 `blocked: yes`，并在 `blocker` 写：现象 + 已尝试的替代方案和失败原因 + 解除所需条件或人。
- BOARD.md「阻塞」栏必须列出该任务与阻塞原因，不允许静默挂起。
- 阻塞只阻断依赖它的步骤：例如不能重启主服务时，仍继续静态检查、隔离预览、接口直连验证，并在 TASK.md 记录已完成与未完成的分界。
- 阻塞解除后把 `blocked` 改回 `no`，并在阶段流转记录中写解除时间与依据。

## 12. 执行节奏与自检

- 每完成一个阶段：更新 TASK.md → 同步 `tasks/tasks.md` → 更新 BOARD.md → 在对话中回声一次（阶段、证据、下一步）。不要等整条任务结束才汇报。
- 交付前从项目根执行：

```
../Scripts/python.exe -B competitor_insight/check_board.py
../Scripts/python.exe -B scripts/workspace_hygiene.py
```

- `check_board.py` 只读：校验状态块字段、阶段合法性、task_id 与目录一致、阻塞必填、证据目录存在、`tasks.md`/BOARD/HANDOFF 编号双向一致、三方阶段一致、看板分栏归属正确；另校验协议契约（`config/bci_protocol.json` 的 reader 符号存在、verify 真执行）、`frozen_paths` 越界与 `port` 冲突。
- `TASK-COMMITTED` 约束会对 `TESTED`/`LIVE` 任务检查 `commit_paths` 是否已全部入库（未跟踪文件同样算未入库）；因此看板可能因"任务未提交"而不是文档不一致变红，这是真实状态，不得为了变绿去删约束或改阶段。
- 检查器统一输出 `status: success|partial|failed` 与「应查 / 实查 / 命中」计数；`partial` 必须单列未覆盖原因，不得把"未覆盖"显示成 0 条。
- 需要冻结文件时先运行 `../Scripts/python.exe -B competitor_insight/check_board.py --freeze BCI-NNN`；基线写在 `tasks/BCI-NNN/frozen.sha256`。
- 文件落点、备份与清理继续按根 AGENTS.md 与 [docs/directory-hygiene.md](../docs/directory-hygiene.md)；`competitor_insight` 已在 [docs/root-files.json](../docs/root-files.json) 登记为正式根目录。
