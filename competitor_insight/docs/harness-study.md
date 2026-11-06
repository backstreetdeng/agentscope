# DeepSeek Harness 工程方法学习 · 对竞品洞察的适用性评估

- 任务：BCI-003（纯学习与评估，**未改任何业务代码**）
- 日期：2026-11-06（Asia/Shanghai）
- 范围：只回答"这套方法怎么运作、同事怎么用、我们能用哪几条、哪几条不该用、第一步做什么"
- 可信度标注：**〔官方文档〕**= 从官方仓库 raw 实际取回；**〔代码实证〕**= 读到具体文件与行号；**〔推断〕**= 我的判断，未在来源中直接写出

---

## 0. 结论先行

1. Harness 的核心不是"提示词工程"，而是**把 agent 的每个部件都做成可替换插件，并用可打印的组装树 + 仅追加会话日志 + 可执行的校验门禁，保证"说的是什么就是跑的什么"**。〔官方文档〕
2. 同事工程没有用 Harness 的代码，但**搬走了这套骨架里最实用的四件**：真源分层、机器契约 JSON、模型前的确定性硬门、隔离环境的一键验收脚本。〔代码实证〕
3. 对竞品洞察能直接落地的是 **5 条**，其中 4 条是文档/校验器级别的小改动，1 条（硬门+单测）需要先有 `server/`。**不建议**照搬插件树、覆盖率门禁、多级 agent 编排、会话日志迁移链——理由见第 6 节。
4. 最小第一步：加一份 `competitor_insight/config/bci_protocol.json` 机器契约，并让 `check_board.py` 用它校验"任务声称的落点是否真实存在"。改动量约 **1 个新文件 + 30~40 行只读检查**，不碰业务代码。

---

## 1. 三个来源分别读到了什么

### 1.1 官方仓库 `deepseek-ai/deepseek-harness`〔官方文档〕

取用方式与结果：

| 目标 | 结果 |
|---|---|
| `raw.githubusercontent.com/.../master/README.zh.md` | 首次用内置抓取器返回空；改用 PowerShell `Invoke-WebRequest`，**HTTP 200，2511 字节**，取到全文 |
| `github.com/.../blob/master/README.zh.md` | 200，页面正文与 raw 一致（含 latest commit `Sep 29, 2026`） |
| `raw.../master/AGENTS.md` | **HTTP 200，19315 字节**，取到全文（仓库级工程规范） |
| `raw.../master/docs/architecture.zh.md` | **HTTP 200，11326 字节**，取到全文 |
| `api.github.com/.../contents/.agents/skills` | 200，列出 **24 个 skill 目录** |

值得注意（直接影响怎么理解"Harness 的方法"）：

- **README 本身不写方法论**，只有定位、安装运行、社区入口。真正的工程约定分散在三处：仓库根 `AGENTS.md`（规则清单）、`docs/architecture.zh.md`（机制）、`.agents/skills/<name>/SKILL.md`（23 个可执行流程包，如 `dsh-pre-push-checks`、`dsh-error-handling`、`dsh-code-review`、`dsh-prose-standard`）。
- `AGENTS.md` 里几乎每条规则都挂一个**机器门禁**：`verify-cordis-config`、`verify-export-jsdoc`、`verify-doc-budgets`、`verify-application-entrypoints`、`verify-client-ui-i18n`、`test:coverage`（对 `packages/*/*/src` **逐文件 100%**）。也就是"规范靠 CI 拒收来执行，不靠人记"。
- 明确写了 **"Model-visible ⟺ logged"**：任何进入模型请求的内容都必须能从会话日志重建；新增模型可见输入就必须新增一个会话事件。
- 明确写了 **"On an empty `catch` names the error"**、**"Misconfiguration fails loud"**、**"Trust TypeScript at typed same-process boundaries, validate at … model/tool JSON, durable/file, process, wire boundaries"**——失败处理与校验位置是成文规则，不是个人风格。
- 测试策略：`test:coverage` 才是 CI 门禁；`test:snapshot` 是**无 Key 也能跑的会话回放**（keyless recorded-session replay through shipped profiles）；`test:e2e` 无 `DEEPSEEK_API_KEY` 自动跳过。

未读（因此不做断言）：`docs/testing.md` 正文、`docs/defensive-patterns/` 正文、23 个 `SKILL.md` 的具体内容（只看了目录名）、`packages/*` 各包 README。

### 1.2 同事工程 `industry-tracking-v2`〔代码实证〕

读了 7 个文件（路径均为 `D:\colleague\炫琪\CATARC_业务组监测交接\02_工程\workspace\projects\industry-tracking-v2\`）：

| 文件 | 读到的内容 |
|---|---|
| `AGENTS.md`（45 行） | 真源优先级表、当前状态表、角色边界 |
| `WORKFLOW.md`（78 行） | 人工操作唯一真源、启动/验收/密钥约定 |
| `docs/HARNESS.md`（120 行） | 效果公式、14 条铁律、阶段图、阶段记忆、能力清单、分层验收表 |
| `config/tracking_v2_protocol.json`（76 行） | 机器契约：stages / required_tables / cost_gates / hard_gates / runtime_providers / job_contract |
| `scripts/verify_harness.py`（214 行） | 一键验收脚本 |
| `src/industry_tracking_v2/hard_gates.py`（426 行） | 确定性硬门实现 |
| `src/industry_tracking_v2/services/{jobs,provenance}.py`、`cost_gate.py` | 作业状态机、过程留痕、费用门闩 |

其他观察：工程根有 `tests/`（10 个测试文件，HARNESS.md 记录"44 个测试通过"）、`config/`（4 个契约/配置 JSON）、`docs/`（6 篇文档）、`.runtime/`（运行日志）。`AGENTS.md` 第 44-45 行把技能指向 `.cursor/skills/industry-tracking-v2/SKILL.md`，但**项目目录里没有 `.cursor/`**。（**已推翻，见 §5.1**：该 Skill 存在，只是位于 workspace 根）

### 1.3 用户给的两份文档〔代码实证，非独立来源〕

- `..._HARNESS.md` 与 1.2 的 `docs/HARNESS.md` **逐字相同**（120 行）。
- `..._AGENTS.md` 与 1.2 的 `AGENTS.md` **逐字相同**（45 行）。

所以这是**同一个来源的副本，不是第三份独立材料**。它的价值在于把"同事工程的自述规范"固定成可引用的原文，但不能用来交叉印证 1.2 的代码是否真的照做——后者只能靠读代码（第 2 节做的就是这件事）。

---

## 2. 五问

### Q1 · Harness 这套方法的核心机制〔官方文档〕

**第一层：没有内核，只有挂载点。** dsh 把整个产品都做成插件——模型适配器、工具注册表、会话日志，连 agent loop 本身都是插件。所有注册都是"副作用"（`ctx.effect()` / `ctx.on()`），插件卸载时自动撤销。因此"改行为"不是去改循环，而是在旁边挂一个插件或换掉一个 provider。运行中的实例由 profile 按序叠加 bundle 与 patch 组装而成，`dsh --profile web --dump-config` 能把实际生效的完整插件树打印出来——**你跑的是什么，是可以被打印和被审计的**，不是靠读代码猜。

**第二层：能力必须三角色成套。** 每一项可替换能力叫一个 seam，包含 Service Definition（声明接口）、Service Provider（实现）、Consumer（通常是面向模型的工具）。换一个 provider 就换掉整条链路的能力，例如把文件系统与进程指向远程沙箱，Bash、PTY、LSP 就一起搬过去，不需要为每个工具写分支。规则明确"单一角色不构成 seam"，新增能力必须三者一起设计——这防的正是"接口加了、没人实现"或"实现写了、没接消费方"。

**第三层：日志是唯一事实源，规范靠门禁执行。** 会话日志是仅追加的 `SessionEvent` 流，模型历史由它投影出来，UI 也从它渲染，所以"模型可见即已记录"——任何影响模型的东西都必须能重建。持久格式带版本与相邻迁移链，已提交的代际不允许被改名、覆盖或删除（只能新增后继版本）。配套的是把规范变成可执行检查：文档字数预算、导出 JSDoc、i18n 硬编码、文件末尾换行、逐文件覆盖率，全部是 CI 会拒收的 gate，再加一层**无 Key 可回放的会话快照**测试，保证面向用户/模型的行为变化至少有可复现的回归物。

一句话概括这套方法的取舍：**它用"可替换 + 可打印 + 可重放"换取大型多入口产品的可维护性**，代价是抽象层多、概念密度高。

### Q2 · 同事工程**实际**怎么用的〔代码实证〕

它没有引入 Cordis 或 dsh，但把 Harness 的骨架里最实用的部分落成了 5 条具体做法：

| # | 做法 | 证据（文件:行号） | 实际写了什么 |
|---|---|---|---|
| 1 | **真源分层，禁止第二套口径** | `AGENTS.md:15-27` | 六级优先级表：①`trk2_*` 表族 ②产品设计 ②a 搜索网格 ②b 编排/硬门/阶段记忆 ③部署 ④底座对齐 ⑤只读指针 ⑥人工步骤；末尾一行 `✗ tracking_* / policy_lib_* / h5/` 明确禁止写入 |
| 2 | **人读文档与机器契约成对出现** | `docs/HARNESS.md:3`、`config/tracking_v2_protocol.json:5-63` | HARNESS 首行写明"机器契约：`config/tracking_v2_protocol.json`"；契约里用 `stages`、`required_tables`、`cost_gates`、`hard_gates`、`runtime_providers`、`job_contract` 六块把"承诺"变成可被脚本读的数据 |
| 3 | **模型之前先过硬门（确定性优先）** | `hard_gates.py:180-294`、`:46-51`、`:57-78`、`:90-95` | `timeliness_gate()` 先判发布日窗口、正文日期锚点、数据周期；拿不到时间锚点直接 `time_unverified` 拒收（`:288-294`，注释写明"禁止仅凭未知发布日放行"）；另有壳页 URL、乱码文本、地方政策三类硬门，全是纯函数、无模型参与 |
| 4 | **长任务 = 持久 job + checkpoint + 协作停止** | `services/jobs.py:22-23`、`:94-127`、`:135-208`、`:219-247`、`:250-262` | 单写者线程池（SQLite 只能一个写者）；每次进度更新在**同一会话**写库并 `commit` 释放锁（`:124-126`）；停止只置 `cancel_requested`，在单元边界退出；`recover_interrupted_jobs()` 把重启后残留的 `running` 显式改成 `failed/interrupted` 并提示 resume——**不假装还在跑** |
| 5 | **隔离环境的一键验收 + 分层结论** | `scripts/verify_harness.py:39-66`、`:62-84`、`:85-103`、`:105-114`、`:116-181`；`docs/HARNESS.md:99-120` | 脚本用临时 SQLite 与临时 export/provenance/checkpoint 目录（`:39-51`），从契约 JSON 读 `required_tables` 与 `foundation_required_columns` 逐项校验（`:62-84`），校验 `runtime_providers` 的布尔开关（`:85-103`），**故意把费用门闩压到 2 次查询验证它会触发**（`:105-114`），最后跑一条端到端冒烟并检查 DOCX 体积/命名与"有没有把隔壁表族混进来"（`:120-181`）；HARNESS §7 的验收表每行都区分"通过 / 代码通过·外部待验收"，不把未验的写成通过 |

失败处理的两条不对称原则，写得很清楚，也值得抄：**判定类一律 fail-closed**（`jobs.py:164-165` 零文档通过直接抛错、`:181-182` 零成条直接抛错、`timeliness_gate` 无时间锚点拒收），**增强类一律 fail-open**（天罗舆情账号失败只跳过线索，不阻断主链，见 `HARNESS.md:27` 与契约 `runtime_providers.sentiment_clue_fail_open: true`）。

一个要说清的边界：这套东西是给**一条长流水线 + 多个外部 Provider** 设计的。它的复杂度（job 表、checkpoint、provenance 包、费用门闩）在我们现在"选口径 → 查询 → 展示"的短链路上**大部分用不上**，真正可迁移的是它们的**形态**，不是体量。

### Q3 · 对竞品洞察能落地哪几条

按"现在就能做 / 收益明确"排序。每条给落点、对应痛点、依据、改动量。

| # | 落地项 | 落在哪里 | 解决我们现在哪个具体痛点 | 依据 | 改动量 |
|---|---|---|---|---|---|
| 1 | **机器契约 JSON + 校验器读它** | 新增 `competitor_insight/config/bci_protocol.json`；改 `check_board.py` | 现在 `check_board.py` 只校验"文档三方一致"，不知道任务**声称的落点是否真实存在**。BCI-001-L07（`bci.scope` 写了但没有读取方）、L08（`competitor_compare` 没有车型集合入参）就是"文档说接线了、代码里没有消费方"的典型 | `config/tracking_v2_protocol.json:5-63` + `verify_harness.py:62-103` | 新文件 ~40 行 + 检查器 30~40 行 |
| 2 | **验收表加"验证层级"列，禁止把接口 200 写成功能验收** | `competitor_insight/RULES.md` §6、`tasks/_TEMPLATE/TASK.md` §2 | 现在验收从"已接线"直接跳"通过"。BCI-001-L04（2023/2024 定量数据未入库）当初就是把"选项能点"写成了"可用" | `HARNESS.md:99-120`、`AGENTS.md:29-40` | 极小（一处规则 + 模板一列） |
| 3 | **口径判定写成纯函数 + 单测** | 新增 `competitor_insight/server/gates.py`、`tests/test_bci_gates.py`（`server/` 目前尚未创建） | BCI-002-L02：43 维模板只有定义，没有校验器消费，档案写进来不会被判合格；同理"车型集合是否给定""年份是否覆盖""样本量是否达阈值"现在只写在 TASK 文档里 | `hard_gates.py:180-294`、`tests/test_hard_gates.py` | 中（先要有 `server/`） |
| 4 | **证据目录必须有过程留痕 TRACE，而不只是 manifest** | `outputs/competitor-insights/<任务>/<run-id>/`；`docs/artifact-manifest-template.json` 增加 `trace` 字段 | 现在 manifest 只说"产物是什么"，不说**跳过了什么、为什么跳过**。BCI-001 的可用性判定理由（2026 音频未解析等）只存在 TASK 表里，换个 AI 接手就得重新问人 | `services/provenance.py:1`、`:34-81`（MANIFEST.json + traces.json + 每次 compose 的输入/输出 + TRACE.md） | 极小 |
| 5 | **"没查到"要区分"无数据"与"未覆盖"，并 fail-closed** | `competitor_insight/web/bci.js` 空态文案 + 后续 `server/` 查询层 | BCI-001-L03：2026 定性音频未解析，现在是 disabled 选项；一旦上游出现半成品数据，页面会显示"0 条"而不是"该数据源未覆盖"，用户会误判成"没有负面反馈" | `timeliness_gate` 的 `time_unverified` 分支（`hard_gates.py:288-294`）、`jobs.py:164-165` | 小 |

补充一条**可选**（不建议放第一步）：把 BCI-001/002 那种"人开浏览器点一遍"的验收，换成录一次请求/响应再离线回放断言，对应 Harness 的 keyless snapshot。收益真实，但要先有稳定的接口层，现在做会绑死在当前 DOM 上。〔推断〕

### Q4 · 哪几条**不**适用，为什么

| 不适用项 | 为什么不该搬 |
|---|---|
| **一切皆插件 / Cordis 插件树 / profile+bundle+patch 分层** | 这套抽象是为"同一份运行时同时服务 Web、Desktop、npm CLI、SDK、ACP 五个入口"设计的（`docs/architecture.zh.md` "应用启动"节明确列了五个 profile）。竞品洞察只有 7860 一个入口、一条链路，引入装配层只会让下一个接手的人先花时间理解框架再读业务，直接违反项目根 AGENTS.md 的"避免过度设计" |
| **逐文件 100% 覆盖率门禁** | Harness 是开源库，API 是对外承诺，所以要用覆盖率换稳定性。我们的模块依赖真实数据源（7860 后端 + 业务库 + 音频/定量文件），强覆盖率会逼着为不可测的 IO 写 mock，测的是 mock 不是行为 |
| **subagent / team / todo / plan / goal 这套会话编排** | 竞品洞察是确定性查询（选口径 → 查 → 展示），没有需要委派给子 agent 的开放任务；而"任务状态与看板"这一职责我们已有 `tasks.md` + `BOARD.md` + `check_board.py` 在承担，再引入一套 session/goal 是重复建设 |
| **仅追加会话日志作为唯一事实源 + 版本化迁移链** | 我们没有"模型逐轮对话"这个对象可记。可以借它的**思想**（结果必须能从留痕重建，已发布的东西不改写只新增），但不能借实现——那会要求把每次查询都造成一条事件流，成本远超收益 |
| **费用门闩（cost gate）** | 同事工程要防的是"一次一键成刊烧掉几十次搜索 + 模型调用"。竞品洞察现在是本地查询、无按次计费的外部 Provider，暂时没有需要拦的成本；等真接入按量计费的检索/模型 API 再补，且届时直接照 `cost_gate.py:36-60` 的形态写即可 |

### Q5 · 如果要做，最小第一步是什么

**只做 Q3 的第 1 条。**

- 新增 `competitor_insight/config/bci_protocol.json`，先只写三个字段：`tasks`（每个 BCI 编号 → 它承诺的落点文件/接口/页面元素）、`hard_rules`（如"前端不得写死模板名"）、`evidence_required`（manifest + TRACE）。
- 改 `check_board.py`：读该 JSON，对每个任务校验"声称的落点路径存在"（文件存在 / 接口在 `app.py` 里能 grep 到 / DOM id 在 `home.html` 或 `bci.js` 里能 grep 到），不一致就报错退出 1。
- 用 BCI-001、BCI-002 各登记 3~5 条断言做首批验证：**L07/L08/L02 这三条遗留问题应该在第一次跑时就被它抓出来**——如果抓不出来，说明契约设计得不够硬，那就别再往下做第 2~5 条。

改动量：**1 个新 JSON（~40 行）+ `check_board.py` 增加 30~40 行只读检查**，不碰 `web/`、不碰 `app.py`、不重启 7860、不需要浏览器验收。做完仍只到 `DEV_DONE`，由用户在页面上确认没有行为变化后转 `TESTED`。

不建议第一步就做 Q3 的第 3 条（gates.py）：它需要先有 `server/` 查询层，而 tab ②③④ 还没开发，现在写校验器没有消费方——这正是我们批评过的"接口加了没人用"。

---

## 3. 未验证清单（不要当成结论用）

1. 同事工程的 44 个离线测试未在本机运行（副本无 `.venv`，且不应在别人的交接目录里装依赖）。
2. `.cursor/skills/industry-tracking-v2/SKILL.md`：**已推翻（见 §5.1）**——文件存在，位于 workspace 根 `.cursor/skills/`，不在项目目录。上一版据此判断"技能包没有实证"是错的。
3. 官方 23 个 `SKILL.md` 只看了目录名，未读正文，因此"Harness 的 skill 与我们的 Skill 机制是否同构"不作判断。
4. `docs/testing.md`、`docs/defensive-patterns/` 未读，关于测试分层与防御式写法的细节可能有更精确的表述。
5. 官方 README 的 latest commit 显示 `Sep 29, 2026`（取自 GitHub 页面），未核对具体 commit SHA。
6. Q3 第 5 条"空态区分无数据/未覆盖"的具体文案与交互，属我的设计建议〔推断〕，不是来源中的既有做法。

## 4. 读取证据

- 证据目录：`outputs/competitor-insights/BCI-003/20261106-harness-study/`
  - `sources/deepseek-harness-README.zh.md`、`sources/deepseek-harness-AGENTS.md`、`sources/deepseek-harness-architecture.zh.md`：实际取回的官方原文（HTTP 200 快照）
  - `sources/colleague-file-index.txt`：本次读到的同事工程文件清单与字节数
  - `manifest.json`：产物与用途
- 同事工程根：`D:\colleague\炫琪\CATARC_业务组监测交接\02_工程\workspace\projects\industry-tracking-v2\`（只读，未修改）
- 附件原件：`c:\Users\legio\.trae-cn\attachments\c191e154-..._HARNESS.md`、`2ee5065d-..._AGENTS.md`（只读）

---

# 5. 全 workspace 复核（2026-11-06 追加）

> 上一版只读了 `projects/industry-tracking-v2/` **一个子项目**，用户指出完整项目目录是 `D:\colleague\炫琪\CATARC_业务组监测交接\02_工程\workspace`。本节是按整个 workspace 重扫后的补充；**原 §0–§4 原样保留**，被推翻或修正的条目在正文标了「已推翻 / 见 §5」，本节末尾 §5.7 统一汇总。
> 只读复核，未改同事目录任何文件。

## 5.1 先更正上一版的两处事实错误

| # | 上一版说法 | 实际 | 证据 |
|---|---|---|---|
| 1 | `.cursor/skills/industry-tracking-v2/SKILL.md` 在副本中不存在，同事"技能包怎么组织"没有实证 | **存在**，只是不在项目里，而在 **workspace 根** `.cursor/skills/`。项目 `AGENTS.md:44-45` 是相对 workspace 根的指针 | `.cursor/skills/industry-tracking-v2/SKILL.md`（39 行，YAML frontmatter + 何时使用/何时不用/必读真源/常用命令） |
| 2 | 把 `industry-tracking-v2` 当成同事工程的代表 | 它只是 15 个注册项目之一（在场 10 个），且是**在场项目里 4 个没有机器状态 JSON** 的项目之一；用它代表整站会系统性低估约定密度 | `PROJECTS.md:12-28` 注册表（15 行）；`projects/*/config/*status*.json` 实测 10 个在场项目中只有 6 个有 |

另需声明：**这份交接副本不完整**。`PROJECTS.md` 注册 **15** 个项目（`PROJECTS.md:14-28`），`projects/` 下只有 **10** 个目录，缺 `daily-work`、`ppt-auto`、`sales-forecast`、`catarc-engagement`、`auto-opinion-daily-layout-lab` 共 5 个，另缺 `.cursor/rules/_template.mdc` 所指向的 `projects/_template/` 骨架目录；`AGENTS.md` 引用的 `docs/PROJECT-AUDIT.md`、`config/project-requirement-audit.v1.json` 也不在。**涉及缺失项目的判断一律标"未验证"，不做推论。**

> 更正说明：本节初稿把注册项目数写成 17（误把 `.cursor/rules/` 下 17 个 `.mdc` 文件当成项目数）。实际为 15 个注册项目、10 个在场、5 个缺失，`.mdc` 是 16 个项目规则 + 1 个工作区 hub 规则。

## 5.2 结构地图

| 层 | 位置 | 角色 | 判定依据 |
|---|---|---|---|
| **路由层** | `PROJECTS.md` | 唯一路由真源：17 个项目的 ID / 名称 / **状态真源指针** / Agent 真源 / 人工流程 / 工程目录 / 本地资料；再加"项目识别"信号表（`PROJECTS.md:30-79`） | 第 1 行自述「多项目总览（唯一路由真源）」；每行"Agent 真源"列都指向一个 `projects/<id>/AGENTS.md` |
| **通则层** | 根 `AGENTS.md` | 只写"跨项目才成立"的规则：任务生命周期与完成闸门（34-42）、隔离铁律（44-50）、API Harness 通则（52-60）、真源自动落文（62-69）、收工双端对齐（71-91）、断点续跑（98+）、Docker 开箱（136+）、命令输出规范（160+）、新增项目（203+） | 每个二级标题都带"（全项目适用）" |
| **换机层** | `WORKSPACE-MIGRATION.md` | clone/换机/Git 未收录项的唯一人读真源，且**每个排除项都写恢复来源**（53-60） | 第 1-5 行自述"唯一人读真源"并明确"勿在本文件复述逐步操作" |
| **客户端路由** | `.cursor/rules/00-workspace-hub.mdc` + 每项目一个 `.mdc` | `alwaysApply: true` 的 7 条短规则：先读 PROJECTS.md、按最具体前缀路由、工作区根不动、禁止混用 | `00-workspace-hub.mdc:1-16` |
| **技能层** | `.cursor/skills/<project>/SKILL.md` | 每项目一个薄技能包：`何时使用 / 何时不用 / 必读真源表 / 常用命令`，正文全是指针，不复述项目文档 | `industry-tracking-v2/SKILL.md:11-38` |
| **项目约束层** | `projects/<id>/{AGENTS.md, WORKFLOW.md, docs/, config/}` | 10/10 项目都有 AGENTS+WORKFLOW（实测）；docs 数从 0 到 28 不等 | 逐目录统计 |
| **工程目录层** | 可能在 `projects/<id>/`，也可能在**根**（`h5/`、`h5-board/`、`hub/`） | 文档与代码不强制同目录；路由靠 PROJECTS.md 的"工程目录"列 | `PROJECTS.md:14,18,25` |
| **素材层** | `materials/<id>/` | 业务原件与运行数据；进不进 Git 按白名单，不进的有恢复来源 | `WORKSPACE-MIGRATION.md:27-60` |
| **状态层** | 项目内 `config/*status*.json` 或 `docs/<STATUS>.md` / `AGENTS.md` | 不在固定目录，而是**每项目在 PROJECTS.md 表里指一个状态真源**；注册 15 个项目中 9 个指机器 JSON、6 个指活文档 | `PROJECTS.md:14-28` 的"状态"列 + 逐项目实测 |

> 状态层的真实约定是"**一个项目只允许有一个状态入口**"，不是"必须用 JSON"。在场 10 个项目中：6 个有 `config/*status*.json`（catarc-board / catarc-content / catarc-hub / data-foundation / policy-crawler / site-collect-cli），4 个用活文档（auto-opinion-daily / catarc-h5 / industry-tracking-v2 / policy-library）。这更正了本节初稿"6 个项目 JSON、其余活文档"被误读成"整体偏 JSON"的印象。

**角色判定：**

- **主工程 = `policy-crawler`**。依据：`docs/` 28 篇（最多）、双状态文件（`intranet_deploy_status.json` + `site_fetcher_status.json`）、且被两处指定为"成刊范例"（`AGENTS.md:60`、`projects/policy-crawler/docs/HARNESS.md:5`）。
- **模板/骨架 = `projects/_template`**。依据：三处指向它的 `HARNESS.md`（`AGENTS.md:60`、`policy-crawler/docs/HARNESS.md:5`、`PROJECTS.md` §新增项目）。**本副本缺失**，模板正文未验证。
- **历史/实验/待建**：`auto-opinion-daily-layout-lab`（正式与实验副本不得互读，`AGENTS.md:49`）、`h5-board`（"隔离展示版"，`PROJECTS.md:18`）、`catarc-content`（"本地 MVP 实施中；生产未部署"，`PROJECTS.md:27`）、`sales-forecast`（"工程待建"，`PROJECTS.md:20`）。

## 5.3 跨项目约定放在哪一层

| 约定 | 放哪 | 层级 | 是否成对 |
|---|---|---|---|
| 路由与项目识别 | `PROJECTS.md` + `.cursor/rules/*.mdc` | workspace | 成对：人读表 + 客户端强制规则 |
| 隔离（真源/端口/素材/技能） | 根 `AGENTS.md:44-50` | workspace 写死，项目不重复 | 端口表是唯一分配处（5174/5176/5175/18180-18192） |
| Harness 原则 | 根 `AGENTS.md:52-60` 五条 | workspace 定原则 | **成对**：原则在根，细则在 `projects/<id>/docs/HARNESS.md`，模板在 `_template` |
| 断点续跑 / 中间落盘 | 根 `AGENTS.md:98+` | workspace 唯一，项目只放短指针 | 明确"禁止另写互相矛盾的长文" |
| 状态与交接 | 项目内 `AGENTS.md` 的当前状态 / `config/status*.json` / `docs/INTRANET-STATUS.md` | **项目层** | 与 PROJECTS.md 的"状态真源"列成对（表只放指针，不复制状态） |
| 技能 | `.cursor/skills/<id>/SKILL.md` | workspace | 与项目 AGENTS 的真源表互为指针 |
| 证据/产物 | 项目内 `materials/<id>/...`、`checkpoints/`、`exports/` | 项目层 | 与 Git 白名单成对（`WORKSPACE-MIGRATION.md:49`） |

一句话：**workspace 层只写"两个项目同时存在时才成立"的规则**（路由、隔离、通则、收工、换机），项目层写"这个项目具体怎么做"；两层只用指针互链，不复制正文。这与我们 `competitor_insight/RULES.md` §1 的"不复制、不替代全项目规则"是同一思路，但同事把"复制禁令"写到了每一个具体条目的粒度。

## 5.4 `industry-tracking-v2` 里看不到的 7 条做法

| # | 做法 | 证据 | 为什么在单个项目里看不到 |
|---|---|---|---|
| 1 | **三层路由**：人读总表 + 客户端 always-apply 规则 + 每项目技能包 | `PROJECTS.md:8-79`、`00-workspace-hub.mdc:8-15`、`skills/industry-tracking-v2/SKILL.md:24-38` | 项目内只有 AGENTS/WORKFLOW；路由与技能都在根，单看项目目录永远发现不了 |
| 2 | **机器可读状态台账** `status.v1.json`：`ports` / `services` / `phase` / `open_items[{id,status:done|open|blocked,summary}]` / `last_job_counts{selected,skipped,errors,status:partial_success}` / `pointers` | `projects/site-collect-cli/config/status.v1.json:1-89` | `industry-tracking-v2` 恰是少数用散文状态的项目（`PROJECTS.md:22` 指到 AGENTS.md），照它学会漏掉这一形态 |
| 3 | **贯通铁律**：文档/schema 有开关 → 必须有代码读者 → `verify_*` 绿灯；**禁止装饰性 `true`** | `policy-crawler/docs/HARNESS.md:30`（§2 第 2 条） | v2 项目里对应的是"能力清单"，但没把"装饰性 true"写成禁令 |
| 4 | **阶段契约登记**：每个 LLM stage 在 protocol 里登记 `required_llm_fields`，缺字段=事故 | `policy-crawler/docs/HARNESS.md:31` | v2 的 `tracking_v2_protocol.json` 登了表/门闩，没登"模型字段契约" |
| 5 | **可抽检**：每次自动跑的 `skip reason` / `stage method` / 模型名写入响应与 `generation`，监测台可查 | `policy-crawler/docs/HARNESS.md:35` | v2 只落库不留"为什么跳过" |
| 6 | **任务模式分类 + 完成声明 + 委派分区**：先判 `read/diagnose/change/publish/long-run`；交付末尾带 `<!-- agent-dod: mode=…; scope=…; verify=…; ssot=…; status=pass|blocked -->`；并行写必须文件不重叠、同一台账只一个写入者 | `AGENTS.md:38-42` | 单项目文档不谈"多 Agent 怎么并存" |
| 7 | **口述规则当轮落文 + 收工只改既有台账**：禁止新开会话日记；有状态变化必须改，无状态变化不许硬改 | `AGENTS.md:62-69`、`71-91` | v2 的 HARNESS 讲"阶段记忆"，不讲"人和 Agent 的交接纪律" |

## 5.5 对原 5 条可落地建议的修正

| 原 # | 原结论 | 复核结论 | 依据 | 改法（落点） |
|---|---|---|---|---|
| 1 | 机器契约 JSON + 校验器读它 | **加强**：契约本身不够，要按"贯通铁律"同时检查"有读者 + `verify` 绿" | `policy-crawler/docs/HARNESS.md:30` | `competitor_insight/config/bci_protocol.json` 每项除"落点路径"外必须有 `reader`（文件:符号）与 `verify`（命令）；`check_board.py` 三条都查 |
| 2 | 验收表加"验证层级"列 | **修正**：列是给人看的，同事用 `open_items[]` 让人和脚本都能读；手写列 + 手写看板会继续双写漂移 | `status.v1.json:38-79`；我们三处（TASK/tasks.md/BOARD）本来就靠 `check_board.py` 强同步 | TASK.md 验收项加 `status: done|open|blocked` + `verify` 字段，BOARD 由脚本生成，不再手抄 |
| 3 | 口径判定写纯函数 + 单测 | **加强**：补"可抽检"——不止判定结果，判定方法与跳过原因也要落字段 | `HARNESS.md:32,35` | `server/gates.py` 返回 `{ok, rule_id, reason}`；查询结果带 `skipped[]` 与 `stage_method` |
| 4 | 证据目录必须有 TRACE | **加强**：除过程叙述，还要 `pointers`（本次用到的定义/DB/脚本入口），让下一个人不用问人 | `status.v1.json:80-88` | 证据 `manifest.json` 增加 `pointers` 段 |
| 5 | "没查到"区分无数据 / 未覆盖 | **保留**，并给出字段形态：`status: success|partial|failed` + `counts{selected,skipped,errors}`，`partial` 不允许渲染成"0 条" | `status.v1.json:27-35`、`jobs.py` 的 `zero-doc` fail-closed | `web/bci.js` 空态 + 后续 `server/` 查询层共用这套枚举 |

## 5.6 漏掉的两条（新增 #6、#7）

**#6 任务级隔离声明与冻结清单。** 同事把"真源不交叉 / 命令不交叉 / 素材不混放 / 技能不混用"写成 workspace 铁律（`AGENTS.md:44-50`），且端口有唯一分配表（47 行）。我们 `RULES.md` §2 只写了"代码落点在哪"，没写"谁在写、哪些文件冻结、占哪个端口"。**最小做法**：`bci_protocol.json` 增加 `owner`、`port`（7860）、`frozen_paths`。`frozen_paths` 不是形式主义——本轮就出现过"以为没人会动 `nev_user_insight_template`"的风险点，冻结清单能让 `check_board.py` 在 diff 里直接报出来。

**#7 任务模式分类决定验收强度。** 同事每条任务先判 `read / diagnose / change / publish / long-run`（`AGENTS.md:38`），不同模式走不同闸门。我们现在没有这个字段，于是 BCI-003 这种纯学习任务只能在 TASK 里手工解释"QA/TESTED 不适用"——**这个解释成本本身就是缺字段的证据**。**最小做法**：TASK 状态块加 `mode: read|change|publish`，`mode: read` 只要求证据与结论，不套测试门禁。

**明确不采用：`agent-dod` 隐藏声明**（`AGENTS.md:42`）。它服务于"Agent 在聊天里交付、平台解析回复"的形态；我们的可校验物在 TASK.md 与证据目录，写进对话不产生任何可被脚本读取的东西。等价物已有雏形：阶段流转记录里每行强制带"依据 + 证据"两列。

## 5.7 结论变化汇总

| 原结论 | 现在 | 说明 |
|---|---|---|
| §0-2「同事工程搬走了四件」 | **修正为五件** | 漏掉最重要的一件：三层路由与"贯通断言"。四件→五件：真源分层、机器契约、确定性硬门、隔离验收、**贯通断言（有读者+verify）** |
| §1.2 / §3-2「Skill 无法核验」 | **推翻** | SKILL.md 在 workspace 根，已读到 |
| §2 Q4「不适用」五条 | **保留** | 插件树、覆盖率、agent 编排、会话日志迁移链、费用门闩仍不适用；**新增一条不适用：agent-dod** |
| §2 Q5「最小第一步」 | **保留，内容变具体** | 仍只做第 1 条，但契约项要含 `reader` + `verify` 两项，否则会退回"装饰性 true" |
| §0-3「能落地 5 条」 | **仍 5 条 + 新增 2 条** | 新增 #6 冻结清单、#7 模式分类；两条都是小改动，且 #7 能直接消掉我们现在的解释成本 |

## 5.8 本轮读取证据

- `outputs/competitor-insights/BCI-003/20261106-workspace-rescan/colleague-workspace-index.txt`：本次读到的 workspace 文件清单、行数与项目目录统计
- `.../manifest.json`：范围、产物、可复现命令
- 同事 workspace 根：`D:\colleague\炫琪\CATARC_业务组监测交接\02_工程\workspace\`（只读，未修改）
