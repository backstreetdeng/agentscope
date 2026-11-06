# 竞品洞察 · 最近交接

更新：2026-11-06（Asia/Shanghai）。新条目追加在最上面。写法见 [RULES.md](RULES.md) 第 9 节；本文件与 TASK.md 冲突时以 TASK.md 为准。

## 2026-11-06 · BCI-005 追加 TASK-COMMITTED（任务必须入库）

- **当前任务与阶段**：[BCI-005](tasks/BCI-005/TASK.md) 仍为 `DEV_DONE`（`blocked: no`），本轮只追加"入库"约束，未改任何任务阶段；BCI-001/002 仍 `TESTED`，BCI-003/004 仍 `DEV_DONE`。
- **本次改动**：只改任务机制，**未碰业务代码**，未重启 7860。`config/bci_protocol.json` 增第 5 条 `TASK-COMMITTED`；`config/verify/verify_constraints.py` 增 `check_task_committed()`；`RULES.md` §6 增"入库是阶段准入硬条件"、§5 增 `commit_paths` 字段、§12 增"看板可能因未入库如实变红"；`tasks/_TEMPLATE/TASK.md` 增 `commit_paths`；BCI-001~005 的 TASK.md 各补 `commit_paths`；`BOARD.md` 增「入库状态」栏；`tasks/tasks.md`、本文件同步。
- **判定方式**：对 `TESTED`/`LIVE` 任务，取其 `commit_paths` 在仓库根执行 `git status --porcelain -- <paths>`；有任何输出（含未跟踪）即 FAIL。`LIVE` 追加 `git rev-list --count @{u}..HEAD`，无上游一律 FAIL。`commit_paths` 留空/`none` 直接 FAIL，不能靠不写绕过。
- **已运行测试与结果**：临时 git 仓库 6/6 反向用例符合预期（干净 PASS、已跟踪未提交 FAIL、未跟踪 FAIL、提交后 PASS、LIVE 无上游 FAIL、未声明 FAIL）；原有 9 个反向用例仍 9/9；`check_board.py` 当前如实 `status: failed`（应查 177 / 命中 1），失败原因就是 BCI-001 7 处、BCI-002 6 处未入库；`workspace_hygiene.py` PASS。
- **未解决问题**：L05 存量任务全部未入库、看板为红（用户将在 BCI-004 完成后统一入库）；L06 `commit_paths` 靠人工声明，写窄会漏判；L01~L04 见 TASK.md §6。
- **下一步与负责人**：用户复核并通过后，先完成统一入库，再让 BCI-005 转 `TESTED`；BCI-001/002 在入库前不得转 `LIVE`。
- **Git**：全部未提交；`competitor_insight/` 整体未跟踪；未执行 `git add` / `commit` / `push`。

## 2026-11-06 · BCI-004 43 维覆盖率只读实测（续）

- **当前任务与阶段**：[BCI-004](tasks/BCI-004/TASK.md) → `DEV_DONE`（`blocked: no`）；本轮只做可行性核实与方案修订，**未写业务代码、未建表**。
- **本次改动**：新增 `competitor_insight/docs/coverage.csv`（43 维逐维：应查 63 / 实查 63 / 命中 / 三态 / 直接命中 / LLM 原料 / note）；更新 `docs/archive-tab-design.md`（header 记录 Q1/Q2/Q9 决议；§6.1 改实测；§6.2 预判表整体替换为实测表；新增 §6.3 四问直答与 10 人试点名单；§6.4 补数原则；§8.1 增加 Q11/Q12；§0 增加 D8/D9）；新增 `outputs/competitor-insights/BCI-004/20261106-coverage/`（`manifest.json`、`coverage.py`、4 份日志）；同步 `tasks/BCI-004/TASK.md`、`tasks/tasks.md`、`BOARD.md`、本文件。
- **实测结论**：43 维 success 19 / partial 16 / failed 8；必填 38 维 17/14/7。8 个无来源维度 = KOL/KOC、首选率、RT 了解渠道/吸引力排序/顾虑/期望、接待期待、老车主复购。全库仅 3 人提及埃安、0 人是埃安车主；满意度有明确分数者 13/63；性别标签全量未提及。
- **10 人试点**：R003/R050/R057（全库仅 3 个埃安提及者）+ R030/R025/R037/R046/R005/R010/R062，覆盖 4 城市 3 种购车属性。
- **已运行检查**：数据库全部为只读 `SELECT`；`check_board.py`、`scripts/workspace_hygiene.py` 结果见下条。
- **未解决问题**：L01（Q3/Q5–Q8/Q10–Q12 待确认）、L03（DDL 未执行）、L05/L07/L08（无来源、性别缺失、评分稀疏）、L06（未提交）。明细见 TASK.md §8。
- **下一步与负责人**：用户复核 `coverage.csv` 与方案 §6；确认后 TRAE 落 `source-map.json`，再按 §7 进入开发。**未执行 `git add` / `commit` / `push`。**

## 2026-11-06 · BCI-005 任务机制 Harness 化（契约 / 三态 / 冻结）

- **当前任务与阶段**：[BCI-005](tasks/BCI-005/TASK.md) → `DEV_DONE`（`blocked: no`），等用户复核机制输出；BCI-001/002 仍 `TESTED`，BCI-003/004 仍 `DEV_DONE`，本轮未改它们的状态。
- **本次改动**：只改任务机制，**未碰业务代码**（`app.py`、`home.html`、`web/bci.js`、`bci.css`、`templates.json`、`templates/*` 均未改），未重启 7860。新增 `competitor_insight/config/bci_protocol.json`（4 条约束，含 id/statement/reader/verify）与 `config/verify/verify_constraints.py`（只读真断言脚本）；改 `check_board.py`（协议 reader/verify 校验、敷衍 verify 拦截、`Tally` 三态计数、`frozen_paths` 越界、`port` 冲突、`--freeze`）；改 `tasks/_TEMPLATE/TASK.md`（增加 `port`/`frozen_paths`）、`RULES.md` §5/§12、`tasks/tasks.md`、`BOARD.md`、本文件；新增 `tasks/BCI-005/` 与 `tasks/BCI-005/frozen.sha256`。
- **兼容策略**：`port`/`frozen_paths` 为可选字段，存量 BCI-001~004 未声明时按「未声明 = 不限制」处理；运行后仍全部 PASS（应查 171 / 命中 0）。
- **已运行测试与结果**：4 条协议约束单跑 success；`check_board.py` success（命中 0）；9 个反向验证用例全部符合预期（4 条 verify 破坏→FAIL→恢复→PASS、reader 符号缺失→FAIL、敷衍 verify→FAIL、冻结文件越界→FAIL 且按字节还原后 PASS、port 非整数→FAIL、port 冲突→FAIL）；`workspace_hygiene.py` PASS。证据：`outputs/competitor-insights/BCI-005/20261106-harness-adoption/`（`verify.log`、`reverse-verify.log`、`git-status.txt`、`manifest.json`）。
- **未解决问题**：BCI-005-L01 业务接口三态未落地；L02 reader 仅词法存在性检查；L03 冻结基线未纳入 Git；L04 未提交。
- **下一步与负责人**：用户复核 `check_board.py` 的三态输出与 `reverse-verify.log`，确认后 TRAE 转 `TESTED`。
- **Git**：全部未提交；`competitor_insight/` 整体未跟踪，工作区还有其他任务改动，不得整体暂存。

## 2026-11-06 · BCI-004 用户洞察档案 tab 技术方案（首轮，已被上条取代）

- **当前任务与阶段**：[BCI-004](tasks/BCI-004/TASK.md) → `DEV_DONE`（`blocked: no`），只交付方案，等用户拍板；[BCI-001](tasks/BCI-001/TASK.md)、[BCI-002](tasks/BCI-002/TASK.md) 仍为 `TESTED`，[BCI-003](tasks/BCI-003/TASK.md) 仍为 `DEV_DONE`，本轮未改它们的状态。
- **本次改动**：只新增文档与证据，**未改任何业务代码、未改模板/`templates.json`/`bci.js`/`bci.css`/`home.html`/`app.py`、未建表、未启动 7860**。新增 `competitor_insight/docs/archive-tab-design.md`（8 部分：架构、数据模型、模板驱动、接口、前端、数据现状、任务拆分、风险）；新增 `tasks/BCI-004/TASK.md`；新增 `outputs/competitor-insights/BCI-004/20261106-archive-design/`（`db-probe.log`、`manifest.json`）；改 `tasks/tasks.md`、`BOARD.md`、本文件；修正 `tasks/BCI-003/TASK.md` 两处把 Harness 落地建议编为 BCI-004 的文字（编号改为另行确认）。
- **关键决策**：档案存 PG 长表（`bci.archive` + `bci.archive_field`，模板版本 + 模板快照，升级不覆盖）；维度 → 题号/标签/元数据的映射放独立 `source-map.json`；确定性直取优先，LLM 只做综合且只返回候选证据 ID；后台 job + 轮询；导出真 xlsx（openpyxl）+ 单人 md；v1 不做自由指令与多人并排。
- **已运行测试与结果**：`check_board.py` PASS；`scripts/workspace_hygiene.py` PASS。未跑：任何业务测试（本轮无业务代码）；数据库只读探查因 192.168.3.146:5432 超时未成功，已记录在 `db-probe.log`。
- **未解决问题**：BCI-004-L01（10 个开放问题待用户拍板）、L02（数据库不可达，S1 阻塞）、L03（`bci` schema DDL 未获批）、L05（排序类/RT 类维度可能无数据）、L06（未提交 git），明细见 TASK.md §8 与 [BOARD.md](BOARD.md) 挂账表。
- **下一步与负责人**：用户确认方案 §8.1 的 Q1–Q10（至少 Q1/Q2/Q3/Q4/Q9），TRAE 再执行 S1 覆盖率盘点与 source-map。
- **Git**：全部未提交、未暂存；工作区仍混有其他任务改动，不得整体暂存。

## 2026-11-06 · BCI-003 Harness 工程方法学习与适用性评估

- **当前任务与阶段**：[BCI-003](tasks/BCI-003/TASK.md) → `DEV_DONE`（`blocked: no`），等用户阅读确认；[BCI-001](tasks/BCI-001/TASK.md)、[BCI-002](tasks/BCI-002/TASK.md) 仍为 `TESTED`，等 7860 验收。
- **本次改动**：只新增文档与证据，**未改任何业务代码**。新增 `competitor_insight/docs/harness-study.md`（五问结论 + 三源可信度标注 + 未验证清单）；新增 `outputs/competitor-insights/BCI-003/20261106-harness-study/`（官方三份原文快照、同事工程读取清单、`manifest.json`）；改 `tasks/tasks.md`、`BOARD.md`、本文件，新增 `tasks/BCI-003/TASK.md`。
- **已运行测试与结果**：`check_board.py` PASS；`scripts/workspace_hygiene.py` PASS。未跑：同事工程 44 个离线测试（交接副本无虚拟环境，不在他人目录装依赖）。
- **未解决问题**：BCI-003-L01（Q3 五条均未落地，等用户决定是否立项）、L02（同事 Skill 与官方 SKILL.md 正文未核验）、L03（未提交 git）。
- **下一步与负责人**：用户读 `docs/harness-study.md` §2 Q3/Q5，确认是否另立任务落地机器契约（TRAE 执行）。
- **Git**：全部未提交，工作区仍有其他任务改动，不得整体暂存。

## 2026-11-06 · BCI-002 模板 v1 交付 + 模板下拉改为读清单

- **当前任务与阶段**：[BCI-001](tasks/BCI-001/TASK.md) → `TESTED`（`blocked: no`）；[BCI-002](tasks/BCI-002/TASK.md) → `TESTED`（`blocked: no`）。两者均等用户 7860 验收。
- **本次改动**：新增 `competitor_insight/templates/`（`nev_user_insight_template.json` 8 组 43 维、`nev_user_insight_template.md` 人读版、`README.md`）；新增 `competitor_insight/web/templates.json` 下拉清单；改 `bci.js`（模板选项改为运行时 fetch 清单，`enter()` 先加载再 `restore()`，加载失败走不可选降级）；`bci.css` 上一轮已改 2×2 布局，本轮未动。
- **已运行测试与结果**：`validate_template.py` 25/25 PASS（`outputs/competitor-insights/BCI-002/20261106-template-v1/`）；`verify_selector.py` 39/39 PASS（`outputs/.../BCI-001/20261106-datasource-selector-r2/`，含 4 张截图与 manifest）；`check_board.py` PASS；`scripts/workspace_hygiene.py` PASS。已知基线：`GET /api/health` 404。
- **未解决问题**：BCI-001-L02～L08、BCI-002-L02～L03（L01 已关闭）；模板尚无后端校验器消费维度定义。
- **下一步与负责人**：用户在 7860 验收模板下拉可选并确认上线（TRAE 转 `LIVE`）；未获指令不开发 tab ②。
- **Git**：全部未提交，工作区还有其它任务改动，不得整体暂存。

## 2026-11-06 · 工作区改名 + 代码收拢 + 任务总表 + BCI-001 重做完成

- **当前任务与阶段**：[BCI-001](tasks/BCI-001/TASK.md) 竞品洞察 · 数据源筛选 tab → `TESTED`（`blocked: no`）；[BCI-002](tasks/BCI-002/TASK.md) 新能源用户洞察模板 → `CREATED`（`blocked: no`）。
- **结构调整**：目录 `competitor_insights` → `competitor_insight`；前端资源收进 `competitor_insight/web/`（`bci.js`、`bci.css`），由 `app.py` 的 `/competitor-insight/` 路由提供；新增 `tasks/tasks.md` 任务总表；`check_board.py` 改为校验 `tasks.md` ↔ `BOARD.md` ↔ 各 `TASK.md` 三方一致。
- **已改文件与 git 状态**：新增 `competitor_insight/`（含 README、RULES、BOARD、HANDOFF、check_board.py、tasks/、web/，未跟踪）；修改 `app.py`（新增 `/competitor-insight/` 静态路由与 `_send_file` 白名单，删除 `POST /api/bci/datasource/availability` 及白名单项）、`home.html`（左导航 `bci`、视图骨架、资源引用、四类选择器瘦壳）、`assets/home.js`（删除内联 BCI 模块，仅保留挂载桩）、`assets/home.css`（BCI 样式移出）、`docs/root-files.json`（根目录名同步）。**全部未提交**，工作区同时存在其他任务改动，不得整体暂存。
- **已运行测试与结果**：`verify_selector.py` 29/29 PASS，EXIT=0（证据 `outputs/competitor-insights/BCI-001/20261106-datasource-selector-r2/`，含 `verify.log`、2 张截图、`manifest.json`）；`check_board.py` PASS；`scripts/workspace_hygiene.py` PASS。已知基线：`GET /api/health` 404，与本次改动无关。未跑：多用户/并发口径、tab ②③④（未开发）、全项目回归。
- **未解决问题**：BCI-001-L01～L08、BCI-002-L01，明细见各自 TASK.md 与 [BOARD.md](BOARD.md) 的遗留挂账表。
- **下一步与负责人**：用户在 7860 验收「竞品洞察 → 数据源筛选」并确认上线（TRAE 转 `LIVE`）；BCI-002 由 TRAE 按埃安RT 报告章节产出模板。未获指令前不主动开发 tab ②。
- **环境提示**：`app.py` 启动时把 `home.html` 读进内存，前端结构改动必须重启 7860；`competitor_insight/web/*`、`assets/home.js`、`assets/home.css` 按请求读盘。重启前先确认月报专用浏览器状态，遵守根 AGENTS.md 保护规则。

## 机制落地说明（2026-11-06）

- 采用任务制机制，取代此前以临时对话推进的方式。
- 目录与入口：`competitor_insight/README.md`、`RULES.md`、`BOARD.md`、`HANDOFF.md`、`check_board.py`、`tasks/_TEMPLATE/TASK.md`、`tasks/BCI-001/TASK.md`、`tasks/BCI-002/TASK.md`、`tasks/tasks.md`；`docs/root-files.json` 登记根目录 `competitor_insight`。
- 此后竞品洞察的开发、修复、验证、上线一律先落任务再动手；成果物必须落成文件。
