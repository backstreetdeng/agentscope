# 竞品洞察看板 · BOARD

- 更新：2026-11-08（Asia/Shanghai）
- 状态源：各 `tasks/<编号>/TASK.md`；`tasks/tasks.md` 与各 TASK.md 同步。三者冲突时以 TASK.md 为准，并同时回改总表与本文件。
- 一致性检查：`../Scripts/python.exe -B competitor_insight/check_board.py`（校验 `tasks.md` ↔ `BOARD.md` ↔ 各 `TASK.md` 三方一致；不通过不得声称阶段完成）。
- 阶段定义与准入条件见 [RULES.md](RULES.md) 第 6 节。

## 晨间速览（2026-11-08 晨）

> **一句话**：六个任务全部有结论、全部入库并已推送（`origin/feature/user-insight-t0-t4` = `6775c56`，本地与远端 0/0）；`check_board.py` **PASS**（应查 199 / 实查 199 / 命中 0）。今晚只做了把关与收尾，没有新功能。剩下的都是**你验收**和**三件要你拍板的事**，不是开发。
>
> 7860 仍在运行：`GET /api/bci/analysis/models` 与 `GET /competitor-insight/templates.json` 实测 200。若明早打不开，按 `start_agent.cmd` 常规启动（先看下面「坑」第 6 条）。
>
> **安全提醒（未变）**：仓库 `backstreetdeng/agentscope` 为**公开**仓库；`1bd7eee` 中 `20261106-coverage/coverage.py` 硬编码的 `vectordb` 口令与当前 `.env.new-car` 仍相同，属有效凭据暴露（BCI-004-L11，未修）。

| 任务 | 阶段 | 是否入库 | 最近提交 | 剩余遗留（未关闭） |
|---|---|---|---|---|
| [BCI-001](tasks/BCI-001/TASK.md) 数据源筛选 | TESTED | 已入库 | `1bd7eee`（声明收窄 `9cf1c03`） | L02/L03/L04 数据缺口、L05 剩余 tab、L07 scope 无消费方、L08 工具无车型入参 |
| [BCI-002](tasks/BCI-002/TASK.md) 洞察档案模板 | TESTED | 已入库 | `1bd7eee`（收窄 `f432794`） | L01 新车型模板、L02 无后端校验器、L04 12 组 vs 13 组、L05 取值类型为推断、L06 待验收（BCI-004 已交付） |
| [BCI-003](tasks/BCI-003/TASK.md) Harness 学习 | DEV_DONE | 已入库 | `1bd7eee` | L01/L05 五条建议未立项、L02 官方 SKILL 正文未读、L04 交接包缺 5 项目 |
| [BCI-004](tasks/BCI-004/TASK.md) 洞察档案 tab | TESTED | 已入库 | `7dc91aa` → `01da692`（枚举归一 + 渠道归并） | L01 开放问题、L05/L07/L08 数据缺口（**已决策维持**）、L10 schema 属主、L11 口令 |
| [BCI-005](tasks/BCI-005/TASK.md) 任务机制 | DEV_DONE | 已入库 | `1bd7eee` | L01 业务接口无三态、L02 reader 仅词法检查、L06 commit_paths 靠人工声明（L07 已决策不修） |
| [BCI-006](tasks/BCI-006/TASK.md) 即时分析 tab | TESTED | 已入库 | `5e8f964`（文档 `ca18f37`；已推送 `6775c56`） | L01 无排序题、L03 无胜出观测题、L05 无级别字段、L06 定性归类为启发式、L07 v1 不做 |

### 等你拍板的三件事

| # | 事项 | 为什么需要你定 | 我的建议默认值 |
|---|---|---|---|
| 1 | **`vectordb` 口令是否轮换 / 仓库是否转私有** | 仓库是公开的，`1bd7eee` 里硬编码的口令与现用口令一致，等于凭据公开 | **今天轮换口令**并同步 `.env.new-car`；仓库可继续公开。若暂不轮换，请在 BCI-004-L11 记「接受风险」，不要扩大可见范围 |
| 2 | **`bci` schema 属主** | 现状属主 `vectordb`，4 张表属主 `user_insight_loader`，loader 读写建表均正常；`vectordb` 执行 ALTER 报 `must be member of role "user_insight_loader"`（42501） | **维持现状**即可（L10 保持开启）；若要转，找 `postgres`/DBA 执行 `ALTER SCHEMA bci OWNER TO user_insight_loader;`，应用无需改动 |
| 3 | **7860 验收后是否转 LIVE** | BCI-001/002/004/006 四个 tab 都停在 `TESTED`，只有你验收才能转 `LIVE` | 今天验收四处（数据源筛选 / 模板下拉 / 洞察档案 10 人试点 / 即时分析），通过后我统一转 `LIVE` 并推送；BCI-003/005 是否转 `TESTED` 一并给结论 |

**今天最该做的一件事**：**轮换 `vectordb` 口令**——这是唯一一件「已经泄露、且仍在生效」的风险，其余都是验收或等业务补数。

### 今天可能踩的坑（不是遗留，是操作时会遇到的）

1. **全量 63 人档案没跑过**，库里只有 10 人。点「生成」会真实调 DeepSeek 并写 `bci.*`，耗时和费用都会上来；重跑 R046 仍会得到「增购」，但会覆盖 `20261107-r046-verify` 记录的人工修正痕迹，先备份证据再跑。
2. **2023/2024 定量数据未入库**：tab① 仍可勾选这两个年度，但下游无表可查——是数据缺口，不是页面 bug。
3. **车型别名集中在 `config/analysis_models.json`**：库内出现新写法不会自动归并，计数会偏；新增车型必须同时改别名映射并跑 `test_analysis_service.py`。
4. **8 个无来源维、满意度仅 13/63 有分**：导出显示「本期无来源」或空值是 Q11/Q12 既定口径，不要当缺陷修。
5. **根目录 `debug.log` 是搜狗输入法写的**（在 `myproject` 工作目录下），删了会再生；已被 `.gitignore` 排除，别当项目文件提交。
6. **7860 是 detached `python app.py` 进程**：重启前先确认月报专用 Chrome 没在跑（根 AGENTS 保护规则）；`home.html` 在启动时读入内存，改前端必须重启才生效。
7. **`check_board.py` 的 `TASK-COMMITTED` 只看文件级状态**：任何 `TESTED` 任务 `commit_paths` 范围内留了未提交改动就判红，改完文档必须同批提交，别留中间态。

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
| [BCI-006](tasks/BCI-006/TASK.md) | 竞品洞察 · 即时分析 tab | TRAE | 用户明早验收 7860「即时分析」tab；业务确认 §8 数据缺失清单的后续补数范围 | 2026-11-07 |

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
| BCI-004-L12 | ~~标签「首增换购属性」非标准取值~~ 已解除 | 归一前 `实际增购。` 会触发 `invalid_enum` 整人失败 | 用户拍板「实际增购=增购」；D7c 建集中归一层，D7d 增加互斥值 `purchase_type` 回退（一致才取值、缺失/冲突仍 suspect）；全库 2 条非标准已分流 | TRAE | [BCI-004](tasks/BCI-004/TASK.md) |
| BCI-006-L01 | 关注「产品 / 品牌 / 服务第一排序」无题项 | 该指标只有空态 | 业务补排序题或确认改用 16 维勾选率 | 用户/业务 | [BCI-006](tasks/BCI-006/TASK.md) |
| BCI-006-L03 | 「对手为什么赢」无观测题、无未购车样本 | 该指标只有空态，v1 不做推断 | 补未购车/流失样本或竞品侧题项 | 业务 | [BCI-006](tasks/BCI-006/TASK.md) |
| BCI-006-L05 | 车型级别/车身形式库内无字段 | 「同级对比」只能按价格段 | 业务确认级别口径或补数据 | 业务 | [BCI-006](tasks/BCI-006/TASK.md) |
| BCI-006-L06 | 定性 16 维归类为关键词启发式 | 个别原话可能漏归/误归 | 未命中原话单列；后续可接语义模型或人工校对 | TRAE/业务 | [BCI-006](tasks/BCI-006/TASK.md) |
| BCI-006-L07 | 满意度进攻点/被进攻点需跨车差值 | v1 不做，页面不出现 | 业务确认推导口径与对比车规则 | 业务 | [BCI-006](tasks/BCI-006/TASK.md) |

## 入库状态（TASK-COMMITTED）

2026-11-06 已完成首次入库：提交 `1bd7eee`，已推送 `origin/feature/user-insight-t0-t4`。`competitor_insight/` 全部内容与 `outputs/competitor-insights/` 证据（`*.log` 被 .gitignore 排除）已纳入版本跟踪。

| 任务 | 阶段 | 入库状态 | 实测依据 | 剩余动作 |
|---|---|---|---|---|
| [BCI-001](tasks/BCI-001/TASK.md) | TESTED | **已入库** | `commit_paths` 已按「只声明本任务独占文件」收窄（移出 `app.py`/`home.html`/`docs/root-files.json`），`TASK-COMMITTED` 通过；移出理由与盲区见该任务 §6「入库判定边界」 | 今后再改这三个共享文件需人工登记 |
| [BCI-002](tasks/BCI-002/TASK.md) | TESTED | **已入库** | `TASK-COMMITTED` 通过（0 处未入库） | 无 |
| [BCI-003](tasks/BCI-003/TASK.md) | DEV_DONE | **已入库** | 目录与证据随本次提交入库 | 转 TESTED 前复核 |
| [BCI-004](tasks/BCI-004/TASK.md) | TESTED | **已入库** | 提交 `7dc91aa`（59 文件：`server/`、`tests/`、`web/bci-profile.*`、`ops/` DDL、BCI 文档与证据）；`app.py` 仅 4 处 BCI hunk，深度调研等改动未纳入；`*.log` 受 `.gitignore` 限制只在本机 | 用户验收后上线；如需日志入库需先决定 `.gitignore` |
| [BCI-005](tasks/BCI-005/TASK.md) | DEV_DONE | **已入库** | 机制文件与证据随本次提交入库 | 用户复核后转 TESTED |
| [BCI-006](tasks/BCI-006/TASK.md) | TESTED | **已入库（`5e8f964`）** | `analysis_service.py`、配置、前端、6 套测试/脚本、文档与 `outputs/competitor-insights/BCI-006/` 证据；`app.py` 仅 BCI 分析路由 hunk | 用户验收后上线；业务确认 §8 补数范围 |

> 首次入库范围与排除项见 [BCI-005/TASK.md](tasks/BCI-005/TASK.md) 第 4 节 S12；`app.py` / `home.html` / `home.css` / `share-files/TASKS.md` 里其他任务的 hunk 一律未带入。

## 看板维护约定

1. 任务进入/离开某阶段时，同步移动它在分阶段看板中的行；不留两处。
2. 阻塞任务除留在原阶段栏外，必须出现在「阻塞」栏并写清解除条件。
3. 新建任务先写 TASK.md，再加进 `tasks/tasks.md` 与本看板对应阶段栏，最后跑一致性检查。
4. 本文件的标题、负责人、下一步、更新日期必须与 `tasks/tasks.md` 和 TASK.md 状态块逐字一致。
5. 不在本文件记录聊天结论、截图或详细步骤；细节一律在任务 TASK.md 与证据目录。
