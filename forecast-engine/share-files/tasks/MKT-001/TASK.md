# MKT-001 市场板块 · 竞品对标能力

**任务目标**：为市场板块新增【竞品对标】能力——围绕上市新车与发布会竞对态势，自主识别目标车型并建立多维竞品池，融合工信部官方申报（P0）、汽车情报知识库（P2）、联网实时抓取（P1/P2）三大数据底座，经交叉校验后交付精准对标矩阵与战略 So What。

**方法论依据**：deep-research-assistant 插件（研究指挥官四段工作流），2026-11-02 已完成 L2 实测验证，证据存档 `temp/20261102-deep-research-eval/`。

**架构结论**：方法论为语义层（skill 包）、ResearchDAG 泛化为执行层（机制）、三底座为数据层；非 prompt 硬扛，非静态 workflow。

**边界**：不改动市场预测、Chronos-2、月报、周报既有链路（月报红线 2026-11-02 复审后细化：月报文件 git 零改动 + benchmark 引擎禁止 import 月报模块 + 共享依赖行为零改动，见需求文档 NFR6）；内部数据禁止传入联网工具；未经授权不提交/推送/部署。

## 步骤

| # | 步骤 | 产出 | 状态 |
|---|---|---|---|
| S0 | 立项与需求起草 | 本 TASK.md + [需求文档](需求文档.md) v0.1 | 完成，待用户评审 |
| S1 | 需求评审与范围确认 | 需求文档 v1.0，关闭开放问题 | 完成（2026-11-02，四项决议全部关闭） |
| S2 | skill 包结构设计 | `skills/` 包骨架 + SKILL.md/references 竞品对标改造 + 产物契约 | 完成（2026-11-02：包名与专用 agent 已确认，包文件已落地 `skills/competitor-benchmarking/`） |
| S3 | 研究引擎适配 | `utils/benchmark_research_dag.py`（复制自 monthly_research_dag 改造）+ 孪生标记；月报零改动 | 完成（2026-11-02：复制实现 + 8 项单测通过 + dry-run 通过，适配清单见下方核对） |
| S4 | 工信部数据对接 | 接口契约（与用户采集能力对齐）+ 只读工具注册 + 批次对账 | 完成（2026-11-02：miit_* 只读工具 + pz_name 映射表 + car_id 对账，真实库冒烟通过） |
| S5 | 交叉校验规则库 | 字段级规则（P0 锚定/价格阶梯/冲突三型/单元格标注）+ 测试 | 完成（2026-11-02：utils/benchmark_validation.py + validate_matrix.py 落地，12 项单测 + 端到端通过） |
| S6 | MVP 集成 | agent 挂载 + app.py 增量 API + pages/ 新页面 | 完成（2026-11-02：benchmark_agent + app.py 分支 + /benchmark 页面 + 导航，语法/导入验证通过；运行时验证留 S7） |
| S7 | 代表性任务验收 | skill-integration-standard 12 项清单 + 真实对标产物 + 独立验收 | 完成（2026-11-02：引擎真实取证 + 矩阵独立验收 + 故意错误发现 + skill runtime 接入，12 项全部满足，标记「已接入」） |
| S8 | Phase 2/3 细化 | 知识库常驻爬虫方案 + 事件触发自动化方案 | 完成（2026-11-02：方案已细化，见下方 S8 方案） |

## S3 适配清单（复制 benchmark_research_dag 时逐项核对）

来源：2026-11-02 对抗性复审（子代理逐行读码）。🔴 硬门槛漏改即假证据/静默劣化，全部核对通过方可标记 S3 完成。

| # | 级别 | 适配项 | 要求 | 核对 |
|---|---|---|---|---|
| 1 | 🔴 | 失败判定正则（原 :207） | 覆盖 benchmark 链路全部 web 工具的失败文本；错误回执不得记 completed | 已核对（`FAILURE_PATTERN` 覆盖 `web_search_*`/`web_reader_*`；真实失败文本 S4/S6 dry-run 校准） |
| 2 | 🔴 | `domain()` / `DOMAINS`（原 :23, :33-37） | `miit_*` 归内部结构化域；白名单与工具前缀一一对应 | 已核对（`miit`/`reputation` 内部域 + `internet` 兜底；前缀匹配） |
| 3 | 🔴 | fallback/gap 硬编码工具名（原 :251, :423-424, :470） | 逐处替换为 benchmark 工具集；工具不存在时不得静默跳过 | 已核对（`miit_search_declaration`/`reputation_search_source_reviews`/`web_search_*`，dry-run 验证命中） |
| 4 | 🔴 | 回执目录（原 :199 `research-receipts/`） | 改 benchmark 专用目录；节点 ID 规则核查，防双引擎互覆 | 已核对（`benchmark-receipts/`） |
| 5 | 🔴 | 跨模块 import 禁令 | `benchmark_research_dag` 不得 import `monthly_research_dag` 及月报业务模块 | 已核对（单测正则断言语料无 import） |
| 6 | 🟡 | 月报 schema 专属字段（原 :282-287, :396-405） | 有效期/rights 特例/候选字段/new-car 窗口逐项改为对标语义 | 已核对（删除 rights 有效期特例；`structured_candidates` 改 `car_id`/`create_time`/`pz_name`/`pz_value`） |
| 7 | 🟡 | VERSION 与中文提示词（原 :309-357） | 全部提示词去月报化（含"乘用车月报"等字样） | 已核对（`benchmark-research-dag-v1`；提示词全部对标化） |
| 8 | 🟡 | L1 构造器月份语义（原 :266） | 快问快答无月份语义，`month/pages` 签名按对标任务重设计 | 已核对（`month/pages` 改 `target/questions`，无月份语义） |
| 9 | 🟡 | dry-run 真实工具集 | dry-run 挂载真实工具集，否则硬编码工具名漏改无法暴露 | 已核对（用 8 个真实命名 fake 工具验证 fallback/gap 命中） |
| 10 | 🟡 | 共享依赖红线 | `custom_tools.py` 等共享文件行为零改动；确需改动先补最小月报冒烟 | 已核对（仅调用 `record_tool_call`，custom_tools.py 未改动） |
| 11 | 🟡 | 双引擎共存冒烟 | S6 集成后补双引擎同进程共存冒烟测试（回执目录/工具事件不互扰） | 已核对（`tests/test_dual_engine_coexistence.py` 2 项通过） |

## 执行记录

- 2026-11-02（TRAE）：用户确认立项并确定任务编号 **MKT-001**（不沿用预测引擎 CHRONOS 前缀，MKT 系列自 001 起，原 MKT-004 草稿已更名）。完成 S0：需求文档 v0.1 起草。未写任何业务代码。TASKS.md/HANDOFF.md 仅追加本任务条目，既有未提交改动未动。开放问题见需求文档第七节（编号前缀已确认关闭），等待用户评审。
- 2026-11-02（TRAE）：开放问题决议 3/4——①工信部存储建议定为 3.146 `vectordb` 库新建 `miit` schema（DDL 见 [miit-schema.sql](miit-schema.sql)，待用户建表后告知存储路径；导入对账脚本 S4 交付）；②试点范围确认 10–20 万新能源 SUV；③Phase 2 知识库首批源清单经联网调研确定（需求文档第九节：盖世汽车/42 号车库/EET-China，供应链月度数据经财经媒体聚合，口碑复用已有汽车之家+懂车帝数据）。剩余开放问题：前端形态（Q4）。
- 2026-11-02（TRAE）：Q4 前端形态确认——左侧导航栏顶级入口【竞品对标】，与【市场分析】【市场预测】同级。四项开放问题全部关闭，S1 收口（需求文档升至 v1.0）。S2 启动：skill 包结构设计方案已产出（[S2-skill包设计.md](S2-skill包设计.md)），待用户确认后创建 `skills/` 包文件。
- 2026-11-02（TRAE）：S2 确认与落地——用户确认包名 `competitor-benchmarking`、**新建专用 agent**（不复用 market_strategy_agent）。已创建完整包骨架 `skills/competitor-benchmarking/`：SKILL.md（四段工作流竞品对标版 + 红线规则）、agents/default.md（专用 agent 挂载策略）、references×3（evidence-rules / benchmark-matrix / so-what）、assets/matrix-schema.json（矩阵契约）、scripts/validate_matrix.py（验收器接口，规则 S5）与 import_miit.py（S4 占位）、manifest.json（依赖与产物契约）。均为方法论文档与接口占位，未写业务代码。下一步 S3：ResearchDAG 泛化设计。
- 2026-11-02（TRAE）：S3 方案变更（**用户决策：复制而非抽取**）——`monthly_research_dag.py` 完全不动，复制机制为 `utils/benchmark_research_dag.py` 独立演进，适配四耦合点（对标问题源、`miit_*`/`reputation_*`/`web_*` 白名单、L1/L2 预算、矩阵证据接纳）。已知代价：机制双份维护；缓解：文件头溯源标注，出现第三个研究场景再抽公共 core（rule of three）。S3 验收简化：月报文件 git 零改动 + 新引擎自身单测 + dry-run（月报回归门禁不再需要）。需求文档、SKILL.md、agents/default.md、manifest.json、S2 设计、TASKS/HANDOFF 已同步。
- 2026-11-02（TRAE）：miit 表结构检查完成（只读脚本 `temp/20261102-mkt001-miit-inspect/inspect_miit.py`）——3.146 `vectordb` 库 `miit` schema 实际两表：`ods_pz_base_info` 款型基础信息（3,459 行：model_name / type_name / car_id / file_name / create_time）与 `ods_pz_detail_info` 款型明细信息（785,436 行 key-value 长表：pz_name / pz_value，每款型约 227 项，car_id 关联）。**miit-schema.sql 草案（batch/declaration 宽表）作废**。S4 适配要点：硬参数（续航/质量/能耗/电池能量）按 pz_name 映射提取；无公告批次/申报日期字段，P0 锚定暂以 car_id + create_time；file_name 显示源文件为参数配置表（源口径 2026-11-02 用户确认：统一以「款型配置信息」描述，不带来源站点字样）；全字段 nullable、无显式主键，base 表存在多款型共用 file_name（对账按 car_id）。需求文档决议 #1 与难点 #2 已同步。
- 2026-11-02（TRAE）：S3 复制方案对抗性复审完成（独立子代理逐行读码）——**结论：方案可行，但"四个适配点"严重低估实际耦合面**。🔴×2：①失败判定正则为月报专属（Agent Reach / AnySearch / Tavily 标记），漏改则 web 工具错误回执被记 completed，假证据入账本；②`domain()`/`DOMAINS` 前缀白名单漏改则 `miit_*` 落入 internet 域（强制 web_fetch、跳过结构化候选、统计缺项）。🟡：fallback/gap 硬编码工具名共多处、月报 schema 专属字段（有效期/候选字段/new-car 窗口）、VERSION 与中文提示词未列入适配点、回执目录 `research-receipts/` 必须改名防双引擎互相覆盖、L1 快问快答无月份语义需重设计构造器、git 零改动不防跨模块 import、dry-run 须挂真实工具集、红线应扩展为"月报链路（含共享依赖 custom_tools.py 行为）零改动"、S6 后需双引擎同进程共存冒烟测试。处置：S3 动工前将完整适配清单写入本 TASK 逐项核对；五项硬门槛（失败判定正则、domain 白名单、硬编码工具名、回执目录改名、禁止 benchmark 引擎 import 月报模块）纳入 S3 验收标准。
- 2026-11-02（TRAE）：用户两项决议落地——①miit 表数据口径：款型配置信息从站点提取，对外描述统一用「款型配置信息」、不带来源站点字样（SKILL.md、manifest.json、import_miit.py、需求文档背景/FR1/FR3/FR4/难点#2/验收#3/决议#1 已同步；`miit` schema 与 `miit_*` 工具前缀保持不变；Phase 2 口碑源清单中"汽车之家口碑"为既有数据源描述，不在此次范围）。②按复审建议扩展红线并落地适配清单：红线细化写入本文件边界及需求文档 NFR6（git 零改动 + import 禁令 + 共享依赖行为零改动），S3 适配清单（🔴×5 + 🟡×6）已建表落地。下一步：S3 复制实现，按清单逐项核对。
- 2026-11-02（TRAE）：S3 复制实现完成——新增 `utils/benchmark_research_dag.py`（机制复制自 monthly_research_dag，孪生溯源标注，独立演进）与 `tests/test_benchmark_research_dag.py`（8 项单测通过）。适配清单 🔴×5 全通过、🟡×6 中 #6–#10 通过、#11 待 S6（见上方核对列）。月报 `monthly_research_dag.py` git 零改动已核查（git diff 为空）；`custom_tools.py` 仅调用 `record_tool_call` 未改动（其既有 M 为其他任务遗留）。dry-run 证据 `temp/20261102-mkt001-s3-dryrun/`（fallback 覆盖 miit+reputation、gap 命中 web_search）。下一步 S4：miit_* 只读工具注册 + pz_name→标准字段映射表 + car_id 对账
- 2026-11-02（TRAE）：S4 完成——新增 `tools/miit_tools.py`（`MiitSearchModelsTool`/`MiitGetModelDetailTool` 只读工具 + `HARD_PARAM_KEYS` 硬参数映射表 + `MiitService.reconcile` car_id 对账，psycopg2 直连 miit schema 只读账户）与 `skills/competitor-benchmarking/scripts/import_miit.py` 导入+对账实现（CSV 列契约 + 幂等写入 + EXCEPT 对账）。工具命名按实际结构从 `miit_search_declaration`/`miit_get_batch` 调整为 `miit_search_models`/`miit_get_model_detail`（同步 benchmark_research_dag fallback、manifest.json、agents/default.md、测试）。真实库只读冒烟通过：search/detail/hard_params（CLTC/WLTC/NEDC 续航三口径并列 + 整备质量/能耗/电池能量）正常，对账 base 3459 = detail 3459 一致；单测 `tests/test_miit_tools.py` 通过。
- 2026-11-02（TRAE）：S5 完成——新增 `utils/benchmark_validation.py`（`validate_schema` 契约 / `validate_cells` 单元格完整性 / `validate_p0_anchor` P0 锚定 / `validate_price_tiers` 价格阶梯，纯函数规则，不连库）并落地 `skills/competitor-benchmarking/scripts/validate_matrix.py`（支持 `--miit-dsn`，独立脚本可执行，退出码 0/1/2，utf-8-sig 读取）。`tests/test_benchmark_validation.py` 12 项单测通过 + 端到端验证（合法矩阵 passed、硬参数非 P0 返回失败）。P0 硬参数连库对账留 S7 代表性任务验收。
- 2026-11-02（TRAE）：S6 完成——新增 `agents/benchmark_agent.py`（`build_benchmark_agent`，挂载 P0 `miit_*` 本地工具 + P2 `reputation_*` MCP + 联网工具，system_prompt 为竞品对标四段工作流 + 工具优先级 + 红线 + 矩阵 JSON 输出契约）、`model_config/config.json` 加 `competitor_benchmark` agent 配置与 demo_task、`app.py` 增量接入（`COMPETITOR_BENCHMARK_CAPABILITY_ID` 常量 + `run_agent_once` benchmark 分支只加载 reputation 插件 + `/benchmark` 页面路由）、`pages/benchmark.html` 独立页面、`home.html` 左侧导航新增顶级入口【竞品对标】（`nav-item--external`，与市场分析/市场预测同级）。config/import/语法验证通过。未重启 7860 服务（遵守月报浏览器保护规则）。下一步 S7：代表性任务验收 + 独立验收 + skill-integration-standard 12 项。
- 2026-11-02（TRAE）：S7 代表性任务验收 PASS——`temp/20261102-mkt001-s7-acceptance/acceptance.py` 用真实款型配置数据验证：①benchmark_research_dag 引擎 + 真实 miit 工具取证（1 节点 3 证据，`validate_research_ledger` 无错误）②构造对标矩阵 `validate_matrix` 通过 ③故意错误（硬参数 source_tier=P1、单一"价格"维度）均被验收器发现。skill-integration-standard 12 项中已实证：任务图/回执/账本/独立验收/故意错误发现/规则测试覆盖；待 web 运行时接入后补验：run_id 重启恢复、回放下载、skill runtime 隔离运行、agent 真实模型执行验收。本任务整体状态：S0–S8 完成，但按 skill-integration-standard「接入中」（完整 12 项未全过），不得标记「已接入」。
- 2026-11-02（TRAE）：S8 Phase 2/3 方案细化完成（见下方 S8 方案章节）。
- 2026-11-02（TRAE）：S6/S7 补验完成——①双引擎共存冒烟（适配清单 #11）通过：`tests/test_dual_engine_coexistence.py`（2 项）验证 benchmark/monthly 两引擎同进程实例化、回执目录隔离（benchmark-receipts vs research-receipts）、VERSION/domain 白名单互不串扰、共享 reputation 域两引擎均正确归类。②真实模型执行验收 PASS：`build_benchmark_agent` 真实构建（挂载 miit×2 + web×4）+ deepseek 实际执行对标任务（自主识别 钛7/深蓝G318/哈弗猛龙/BJ40/豹5/坦克300 竞品，miit 取硬参数 + tavily 联网取价格口碑，产出 8819 字符矩阵+So What）。过程中发现并修复难点 #8 上下文窗口问题：`miit_get_model_detail` 原返回整表 276 项撑爆上下文（103k token 触发压缩 + 模型 JSON 截断），改为硬参数优先 + 其余明细限量（默认 30、最大 60），修复后真实执行 PASS，全量单测 27 项通过。
- 2026-11-02（TRAE）：skill runtime 接入完成，MKT-001 标记「已接入」——新增 `skills/competitor-benchmarking/agents/openai.yaml`（interface/policy/dependencies，allow_package_scripts + required_artifact_validators=benchmark_matrix）与 `artifact-template.json`（kind=benchmark_matrix，契约 assets/matrix-schema.json + 验收器 scripts/validate_matrix.py），SkillRegistry 校验通过（11 资源 + package_hash）。`activate_skill_runtime` 加 competitor-benchmarking 运行时约束（skill_plan_tasks 建任务图 → miit 取证 → workspace_write_text 写 outputs/benchmark-matrix.json → skill_run_script 跑 validate_matrix → skill_validate_run 终验）；`run_agent_once` benchmark 分支改走 skill runtime（隔离运行 + 任务图 + 检查点 + max_iters=32）。`validate_matrix.py` 支持 SKILL_RUN_ROOT 相对路径解析。`temp/20261102-mkt001-s7-acceptance/skill_runtime_check.py` 验证三项 PASS：隔离工作区（inputs/working/outputs/run-state.json/checkpoints.jsonl）、run_id 恢复（plan 3 节点一致）、回放文件清单（checkpoints + run-state）+ 验收状态机（未完成 failed → 完成 passed）+ runtime 工具覆盖。skill-integration-standard 12 项全部满足。

- 2026-11-03（TRAE）：前端集成修正（用户反馈）——①【竞品对标】由新开独立页改为在右侧主窗口内渲染：`pages/benchmark.html` 改为页面片段，新增 `assets/benchmark.css`（复用 home.css 设计变量、浅色主题）与 `assets/benchmark.js`（fetch `/benchmark-view` 注入 + 事件绑定，与 forecast-engine 同款加载方式）；`home.html` 导航项去掉 `nav-item--external`、改为 `data-view='benchmark' href='#benchmark'` 并新增 `<div id='benchmark-mount'>`；`assets/home.js` MAIN_NAV_KEYS 增加 `benchmark`；`app.py` 新增 `/benchmark-view` 路由，旧 `/benchmark` 302 跳转到 `/#benchmark`。②左侧导航【用户洞察】徽标由 `demo` 改为 `AI`（aria-label 同步为“用户洞察，智能问答与证据回源”）。已验证：接口 200、首页导航与挂载点存在、无 demo 徽标；浏览器实测点击【竞品对标】在右侧主窗口渲染（侧栏保留、URL 为 `/#benchmark`、未开新标签），用户洞察徽标显示 AI。

## S8 方案：Phase 2 知识库爬虫 + Phase 3 事件触发自动化

### Phase 2 知识库常驻爬虫（独立排期，MVP 跑通后启动）
- 源清单见需求文档第九节（首批 盖世汽车 gasgoo.com / 42号车库 42how.com / EET-China；数据聚合 GGII 高工锂电、电池产业创新联盟经媒体转载；口碑复用已有汽车之家+懂车帝；商业采购候选盖世 autodata 配置库）。
- 采集链路：礼貌抓取（UA 标识 + 频控 + robots 尊重）→ 结构化抽取（评测 / 技术拆解 / 供应链选型 / 定性口碑）→ 增量去重（URL + 内容哈希）→ 入库（PostgreSQL 独立 schema，如 `knowledge`）→ 检索（新增 `knowledge_*` 只读工具或并入 reputation 检索）。
- 合规边界：仅公开页面；不绕过反爬（不破解验证码/签名）；版权内容只存摘要 + 链接 + 元数据；微信公众号内容不直接爬。
- 与 MVP 关系：Phase 1 以 `reputation_*` + 联网顶替知识库，本方案为 Phase 2 增量能力，不阻塞 MVP。

### Phase 3 事件触发自动化（Phase 1/2 稳定后）
- 触发源：①款型配置信息新增批次巡检（miit base 表 create_time 增量）②上市/发布会事件监听 ③定时巡检。
- 机制：定时任务扫描新增款型/事件 → 识别目标车型 → 自动创建对标任务（run_id）→ 走 `benchmark_research_dag` 引擎 → 交付矩阵 + So What → `validate_matrix` 验收。
- 调度：独立于 Codex 采集自动化的调度器（周/日级）；未经授权不启用、不部署。
