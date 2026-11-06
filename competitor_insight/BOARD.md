# 竞品洞察看板 · BOARD

- 更新：2026-11-07（Asia/Shanghai）
- 状态源：各 `tasks/<编号>/TASK.md`；`tasks/tasks.md` 与各 TASK.md 同步。三者冲突时以 TASK.md 为准，并同时回改总表与本文件。
- 一致性检查：`../Scripts/python.exe -B competitor_insight/check_board.py`（校验 `tasks.md` ↔ `BOARD.md` ↔ 各 `TASK.md` 三方一致；不通过不得声称阶段完成）。
- 阶段定义与准入条件见 [RULES.md](RULES.md) 第 6 节。

## 晨间速览（2026-11-07 01:25）

> 按实际 Git 与代码状态整理；`check_board.py` 当前 `status: success`（应查 173 / 实查 173 / 命中 0）。7860 已运行，`GET /api/bci/archive/template` 实测 200（43 维 / 12 组）；若明早访问无响应，按 `start_agent.cmd` 常规启动即可。

| 任务 | 阶段 | 入库 | 未关闭遗留 | 解除条件 |
|---|---|---|---|---|
| [BCI-001](tasks/BCI-001/TASK.md) 数据源筛选 | TESTED | 已入库（`1bd7eee`；声明收窄 `9cf1c03`） | L02 新车型模板；L03 2026 定性未解析；L04 2023/24 定量未入库；L05 tab ② 之后仍未开发（tab ② 已由 BCI-004 落地）；L07 `bci.scope` 无后端消费方；L08 `competitor_compare` 无车型入参 | 业务给模板 / 数据解析入库 / 数据入库 / 逐 tab 立项 / 真实读取方验证 / 工具加入参 |
| [BCI-002](tasks/BCI-002/TASK.md) 洞察档案模板 | TESTED | 已入库（`1bd7eee`；声明收窄 `f432794`） | L01 新车型模板；L02 无后端校验器；L04 12 组 vs 原型 13 组；L05 取值类型为推断；L06 洞察档案消费方（已由 BCI-004 交付，待验收） | 业务给模板 / 写入接口落地 / 业务确认分组 / 业务问卷核对 / 用户验收 |
| [BCI-003](tasks/BCI-003/TASK.md) Harness 学习 | DEV_DONE | 已入库 | L01 Q3 五条未落地；L02 官方 23 份 `SKILL.md` 正文未读；L04 交接副本缺 5 项目；L05 §5.6 建议未落地 | 用户决定是否立项 |
| [BCI-004](tasks/BCI-004/TASK.md) 洞察档案 tab | TESTED | 已入库（`7dc91aa`） | L01 Q3/Q5–Q8/Q10 未答；L04 分析指令框未做；L05/L07/L08 数据缺口；L10 `bci` schema 属主为 `vectordb`；L11 `1bd7eee` 历史含旧数据库口令 | 用户验收 + 业务补数 / DBA 改属主 / 用户决定是否轮换口令 |
| [BCI-005](tasks/BCI-005/TASK.md) 任务机制 | DEV_DONE | 已入库 | L01 业务接口无三态；L02 reader 仅词法检查；L06 `commit_paths` 靠人工声明（L07 已决策不修） | 用户复核后转 TESTED；增强按需立项 |

**下一步最该做的一件事**：用户验收 7860 上竞品洞察的三处（数据源筛选 / 洞察档案 10 人试点 / 模板下拉），并顺便拍板 BCI-004-L01 与 BCI-003 的五条建议是否立项；BCI-005 复核后可转 TESTED。

**文档滞后（本轮未改，避免再次产生未提交改动）**：BCI-001-L06、BCI-002-L03、BCI-003-L03 仍写“未提交”，实际已随 `1bd7eee` / `f432794` 入库；BCI-002-L06 与 BCI-001-L05 中“洞察档案 tab 未开发”已被 BCI-004 实现（TESTED）部分取代。下次修改这些 TASK 时一并更正并提交。

## 分阶段看板

### 1. 创建（CREATED）

| 任务 | 标题 | 负责人 | 下一步 | 更新 |
|---|---|---|---|---|
| 暂无 | | | | |

### 2. 执行中（EXECUTING）

| 任务 | 标题 | 负责人 | 下一步 | 更新 |
|---|---|---|---|---|
| 暂无 | | | | |

### 3. 开发完成 · 待验证（DEV_DONE）

| 任务 | 标题 | 负责人 | 下一步 | 更新 |
|---|---|---|---|---|
| [BCI-003](tasks/BCI-003/TASK.md) | 学习 DeepSeek Harness 工程方法并评估对竞品洞察的适用性 | TRAE | 用户阅读 docs/harness-study.md 的 Q3/Q5 与 §5 全 workspace 复核（含 5 条建议修正 + 新增 #6/#7），确认是否立项落地 | 2026-11-06 |
| [BCI-005](tasks/BCI-005/TASK.md) | 竞品洞察 · 任务机制 Harness 化（契约 reader/verify、三态计数、冻结路径） | TRAE | 用户复核 TASK-COMMITTED 与反向验证记录；存量任务须先统一入库，本任务才能转 TESTED | 2026-11-06 |

### 4. 质量验证（QA）

| 任务 | 标题 | 负责人 | 下一步 | 更新 |
|---|---|---|---|---|
| 暂无 | | | | |

### 5. 测试通过 · 待上线（TESTED）

| 任务 | 标题 | 负责人 | 下一步 | 更新 |
|---|---|---|---|---|
| [BCI-001](tasks/BCI-001/TASK.md) | 竞品洞察 · 数据源筛选 tab | TRAE | 用户验收 7860 页面后确认上线 | 2026-11-06 |
| [BCI-002](tasks/BCI-002/TASK.md) | 深访用户洞察档案模板（两份：新能源 / 用户洞察档案） | TRAE | 用户验收 7860 页面下拉两条模板均可选后确认上线 | 2026-11-06 |
| [BCI-004](tasks/BCI-004/TASK.md) | 竞品洞察 · 用户洞察档案 tab | TRAE | 用户验收 7860 页面与 10 人试点数据后确认上线 | 2026-11-07 |

### 6. 已上线（LIVE）

| 任务 | 标题 | 负责人 | 上线入口 | 更新 |
|---|---|---|---|---|
| 暂无 | | | | |

### 7. 阻塞（BLOCKED）

| 任务 | 当前阶段 | 阻塞原因 | 解除条件 | 更新 |
|---|---|---|---|---|
| 暂无 | | | | |

## 全局限留挂账（未关闭）

只列未关闭项，关闭后从本表移除并在任务中标「已关闭 + 证据」。字段含义见 [RULES.md](RULES.md) 第 10 节。

| 编号 | 问题 | 影响 | 解除条件 | 负责人 | 任务 |
|---|---|---|---|---|---|
| BCI-001-L02 | 新车型用户洞察模板缺失 | tab ① 该选项标记「待提供」 | 业务提供模板文件后登记可用性并改为可选 | 用户/业务 | [BCI-001](tasks/BCI-001/TASK.md) |
| BCI-001-L03 | 2026 年定性深访音频未解析 | 2026 选项不可选 | 完成音频转写与解析入库后改为可选 | 业务/数据 | [BCI-001](tasks/BCI-001/TASK.md) |
| BCI-001-L04 | 2023/2024 定量数据未入库 | 选中后下游无表可查，只有源文件 | 完成入库并验证题项对齐，再更新可用性说明 | TRAE/数据 | [BCI-001](tasks/BCI-001/TASK.md) |
| BCI-001-L05 | tab ①②③④ 未开发（含① 洞察档案） | 选完口径还没有消费方 | 逐 tab 建任务并上线 | TRAE | [BCI-001](tasks/BCI-001/TASK.md) |
| BCI-001-L06 | 改动未提交 git | 成果只在工作区 | 用户授权后按文件粒度提交，不夹带其他任务改动 | 用户授权 / TRAE | [BCI-001](tasks/BCI-001/TASK.md) |
| BCI-001-L07 | `bci.scope` 尚无后端消费方 | 多用户覆盖与刷新恢复未验证 | 第二个 tab 落地后由真实读取方验证，并补刷新/多会话用例 | TRAE | [BCI-001](tasks/BCI-001/TASK.md) |
| BCI-001-L08 | `competitor_compare` 无车型集合入参 | 后续洞察对比可能跨全库；本 tab 不受影响 | 工具增加车型集合入参并用真实调用证明结果受约束 | TRAE | [BCI-001](tasks/BCI-001/TASK.md) |
| BCI-002-L01 | 新车型用户洞察模板缺失 | 另一套模板仍不可选 | 业务提供后另立任务或并入本任务 | 用户/业务 | [BCI-002](tasks/BCI-002/TASK.md) |
| BCI-002-L04 | 档案模板分组与原型 13 组不同构（购车对比合并、老车主再购拆出） | 若上游要求严格同构需再调 | 业务确认要 12 组还是 13 组 | 用户/业务 | [BCI-002](tasks/BCI-002/TASK.md) |
| BCI-002-L06 | 「① 洞察档案」tab 未开发 | 模板选了没有消费方 | 由 [BCI-004](tasks/BCI-004/TASK.md) 实现档案表与导出 | TRAE | [BCI-001](tasks/BCI-001/TASK.md) L05 |
| BCI-004-L01 | 未答开放问题：Q3/Q5/Q6/Q7/Q8/Q10/Q11/Q12 | 不阻塞试点骨架，影响 UI 与导出细节 | 用户逐条确认（Q1/Q2/Q9 已拍板） | 用户 | [BCI-004](tasks/BCI-004/TASK.md) |
| BCI-004-L02 | ~~访谈库 192.168.3.146:5432 超时~~ 已解除 | — | 2026-11-06 已连通并完成 43 维实测 | TRAE | [BCI-004](tasks/BCI-004/TASK.md) |
| BCI-004-L03 | ~~`bci` schema DDL 已批准未执行~~ 已解除 | — | 2026-11-07 已建 schema 与 4 表并冒烟通过 | TRAE | [BCI-004](tasks/BCI-004/TASK.md) |
| BCI-004-L05 | 8 维无来源（KOL/首选率/RT 四维/接待期待/老车主复购） | 档案出现空列 | 业务决定留空、补题或补访 | 用户/业务 | [BCI-004](tasks/BCI-004/TASK.md) |
| BCI-004-L07 | 性别/同住人数/用户类型/再购尺寸标签全量未提及 | 年龄/性别只能出年龄 | 补题或留空 | 业务 | [BCI-004](tasks/BCI-004/TASK.md) |
| BCI-004-L08 | 满意度评分仅 13/63 有明确分数 | 无法全员覆盖 | 补问 0–10 分题或接受空值 | 业务 | [BCI-004](tasks/BCI-004/TASK.md) |

## 入库状态（TASK-COMMITTED）

2026-11-06 已完成首次入库：提交 `1bd7eee`，已推送 `origin/feature/user-insight-t0-t4`。`competitor_insight/` 全部内容与 `outputs/competitor-insights/` 证据（`*.log` 被 .gitignore 排除）已纳入版本跟踪。

| 任务 | 阶段 | 入库状态 | 实测依据 | 剩余动作 |
|---|---|---|---|---|
| [BCI-001](tasks/BCI-001/TASK.md) | TESTED | **已入库** | `commit_paths` 已按「只声明本任务独占文件」收窄（移出 `app.py`/`home.html`/`docs/root-files.json`），`TASK-COMMITTED` 通过；移出理由与盲区见该任务 §6「入库判定边界」 | 今后再改这三个共享文件需人工登记 |
| [BCI-002](tasks/BCI-002/TASK.md) | TESTED | **已入库** | `TASK-COMMITTED` 通过（0 处未入库） | 无 |
| [BCI-003](tasks/BCI-003/TASK.md) | DEV_DONE | **已入库** | 目录与证据随本次提交入库 | 转 TESTED 前复核 |
| [BCI-004](tasks/BCI-004/TASK.md) | TESTED | **已入库** | 提交 `7dc91aa`（59 文件：`server/`、`tests/`、`web/bci-profile.*`、`ops/` DDL、BCI 文档与证据）；`app.py` 仅 4 处 BCI hunk，深度调研等改动未纳入；`*.log` 受 `.gitignore` 限制只在本机 | 用户验收后上线；如需日志入库需先决定 `.gitignore` |
| [BCI-005](tasks/BCI-005/TASK.md) | DEV_DONE | **已入库** | 机制文件与证据随本次提交入库 | 用户复核后转 TESTED |

> 首次入库范围与排除项见 [BCI-005/TASK.md](tasks/BCI-005/TASK.md) 第 4 节 S12；`app.py` / `home.html` / `home.css` / `share-files/TASKS.md` 里其他任务的 hunk 一律未带入。

## 看板维护约定

1. 任务进入/离开某阶段时，同步移动它在分阶段看板中的行；不留两处。
2. 阻塞任务除留在原阶段栏外，必须出现在「阻塞」栏并写清解除条件。
3. 新建任务先写 TASK.md，再加进 `tasks/tasks.md` 与本看板对应阶段栏，最后跑一致性检查。
4. 本文件的标题、负责人、下一步、更新日期必须与 `tasks/tasks.md` 和 TASK.md 状态块逐字一致。
5. 不在本文件记录聊天结论、截图或详细步骤；细节一律在任务 TASK.md 与证据目录。
