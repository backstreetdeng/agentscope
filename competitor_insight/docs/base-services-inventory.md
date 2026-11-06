# 竞品洞察共用底座现状盘点（只读）

- 盘点时间：2026-11-06（Asia/Shanghai）
- 盘点范围：`customer_insight/` 下 `quant_service.py`、`retrieval_service.py`、`insight_service.py`、`segment_aliases.py`、`joint_service.py`、`tool.py`
- 盘点方式：静态检索（全仓 import 检索）+ 源码阅读 + 签名抽取。**未改任何代码、未改任务状态、未启动服务、未调用数据库或外部接口。**
- 本文是现状记录，不是改造方案，不含重构建议。

## 结论摘要

1. 六个文件全部是只读数据访问或工具封装，**没有一个直接调用 LLM**；模型归纳发生在使用它们的 Agent 侧。
2. **竞品洞察当前对底座零引用**：`competitor_insight/` 下唯一的 Python 文件是 `check_board.py`（不 import `customer_insight`），`web/bci.js` 也不调用任何 `/api/insight/*` 或 `/api/bci/*`。
3. 真共用的是 `segment_aliases`（三个服务共同依赖）、`quant_service`、`retrieval_service`、`insight_service`（智能问答链路与用户洞察页 API 在用）、`tool.py`（问答 Agent 与市场战略/竞品对标/月报工具集在用）。
4. `joint_service` 名义上被列入共用底座，实际只有用户洞察页的两个 API 和测试在引用，属**用户洞察页专用**。
5. `quant_service`、`retrieval_service`、`insight_service.competitor_compare` 对竞品洞察是「理论上必然要用」的能力，但基于当前代码，仍属**预留共用**，不是已发生的引用。

## 1. 文件清单

行数为文件实际行数（含空行与注释），用于规模判断，不代表有效代码量。

| 文件 | 行数 | 顶部职责（一句话） | 直接调 LLM |
|---|---|---|---|
| `customer_insight/quant_service.py` | 232 | 定量问卷统计服务：按群体维度统计问卷字段分布（只读）。 | 否 |
| `customer_insight/retrieval_service.py` | 700 | 访谈证据检索服务：白名单过滤 → 向量召回 → Reranker 重排 → 证据打包。 | 否 |
| `customer_insight/insight_service.py` | 484 | 洞察服务：圈层画像、满意度痛点、再购意愿、需求配置矩阵等专题洞察（只读）。 | 否 |
| `customer_insight/segment_aliases.py` | 59 | 圈层聚合词 → 库内真实枚举值展开（量化长枚举与访谈短标签的桥接）。 | 否 |
| `customer_insight/joint_service.py` | 113 | 联合洞察服务：组合定性证据 + 战胜战败 + 定量统计，输出配置建议素材。 | 否 |
| `customer_insight/tool.py` | 476 | 用户洞察问答的 Tool 封装层，把五个服务包装成 AgentScope `ReadOnlyBusinessTool`。 | 否 |

## 2. 对外入口（签名级）

仅列对外可调用的函数/类与方法；下划线开头为内部实现，不展开。

### 2.1 `quant_service.py`

- `authoritative_label(question_id: str) -> str`
- `class QuantStatService`
  - `dimensions() -> list[dict[str, str]]`
  - `list_questions(keyword: str = "", limit: int = 2000) -> list[dict[str, Any]]`
  - `stat(question_id: str, group_by: str, top: int = 20) -> dict[str, Any]`
  - `stat_in_group(question_id: str, filter_field: str, filter_value: str, top: int = 10) -> dict[str, Any]`
- 模块常量：`DIMENSIONS`（6 个白名单维度）、`AUTHORITATIVE_GROUPS`（4 个权威题号分组）

### 2.2 `retrieval_service.py`

- `class InterviewRetrievalService`
  - `search(question: str, filters: dict[str, Any] | None = None, top_k: int = 6) -> dict[str, Any]`
  - `battle_search(vehicle_model: str, filters: dict[str, Any] | None = None, top_k: int = 6) -> dict[str, Any]`
- 模块级可调：`_load_env()`（被 `insight_service` 复用）
- 模块常量：`ALLOWED_FILTERS`（city / vehicle_model / purchase_type / question_ids / tag_names / tag_values / respondent_codes）、`DEFAULT_TOP_K=6`、`MAX_TOP_K=8`、`RECALL_LIMIT=30`

### 2.3 `insight_service.py`

- `class InsightService`
  - `segment_clusters(min_samples: int = 30) -> dict[str, Any]`
  - `satisfaction_painpoints(group_field: str, group_value: str, top: int = 10) -> dict[str, Any]`
  - `repurchase_intent(group_field: str, group_value: str) -> dict[str, Any]`
  - `demand_config_matrix(group_field: str, group_value: str) -> dict[str, Any]`
  - `config_detail(group_field: str, group_value: str, top: int = 15) -> dict[str, Any]`
  - `choose_reason_matrix(group_field: str, group_value: str) -> dict[str, Any]`
  - `competitor_compare(focus: str = "attention", min_samples: int = 20, top_models: int = 8, top_dims: int = 5) -> dict[str, Any]`
- 模块常量：`PRODUCT_DIMS`（16 个产品维度）、`SAT_PREFIX` / `ATT_PREFIX` / `CHOOSE_REASON_PREFIX`、四象限标签与阈值

### 2.4 `segment_aliases.py`

- `clear_cache() -> None`
- `distinct_values(conn: Any, table: str, field: str) -> list[str]`
- `expand(values: Iterable[str], available: Iterable[str]) -> list[str]`

### 2.5 `joint_service.py`

- `class JointInsightService`
  - `joint_insight(target_type: str, target_value: str, top_k: int = 6) -> dict[str, Any]`
  - `cross_validation(group_field: str, group_value: str, top_k: int = 6) -> dict[str, Any]`
- 模块常量：`TARGET_MAP`（vehicle_model / purchase_type / age_band）、`QUAL_FIELD_MAP`、`CONFIG_QUESTION`、`CONFIG_QUANT_QID`

### 2.6 `tool.py`

- `build_user_insight_toolkit() -> list[ReadOnlyBusinessTool]`：返回 14 个工具实例。
- 14 个 Tool 类及其 `call` 入参：

| Tool 类 | tool name | `call` 入参 |
|---|---|---|
| `InterviewEvidenceSearchTool` | `interview_evidence_search` | `question, filters=None, top_k=6` |
| `BattleSearchTool` | `battle_search` | `vehicle_model, filters=None, top_k=6` |
| `QuantListQuestionsTool` | `quant_list_questions` | `keyword=""` |
| `QuantStatTool` | `quant_stat` | `question_id, group_by, top=20` |
| `QuantInGroupTool` | `quant_stat_in_group` | `question_id, filter_field, filter_value, top=10` |
| `SegmentClustersTool` | `segment_clusters` | `min_samples=30` |
| `SatisfactionPainpointsTool` | `satisfaction_painpoints` | `group_field, group_value, top=10` |
| `RepurchaseIntentTool` | `repurchase_intent` | `group_field, group_value` |
| `DemandConfigMatrixTool` | `demand_config_matrix` | `group_field, group_value` |
| `ChooseReasonMatrixTool` | `choose_reason_matrix` | `group_field, group_value` |
| `ConfigDetailTool` | `config_detail` | `group_field, group_value, top=15` |
| `CompetitorCompareTool` | `competitor_compare` | `focus="attention", min_samples=20, top_models=8, top_dims=5` |
| `CarSpecWebSearchTool` | `web_search` | 继承 `TavilySearchTool` |
| `CarSpecWebFetchTool` | `web_fetch` | 继承 `WebFetchTool` |

`InterviewEvidenceSearchTool` 同时被 `tools/custom_tools.build_business_toolkit()` 以 `register=False` 复用；`build_user_insight_toolkit()` 内则以 `register=True` 注册全局证据编号。

## 3. 依赖

### 3.1 数据库与外部服务

数据库连接统一来自 `_load_env()`：读取项目根 `.env` 与 `.env.new-car` 的 `NEW_CAR_PG_HOST` / `NEW_CAR_PG_PORT` / `NEW_CAR_PG_DATABASE` / `USER_INSIGHT_LOADER_USER` / `USER_INSIGHT_LOADER_PASSWORD`，缺省为 `192.168.3.146:5432` / `vectordb`。凭据明文只在 `.env`，本文不复制。

| 文件 | 读取的表（schema `user_insight`） | 外部服务 | LLM |
|---|---|---|---|
| `quant_service.py` | `quant_question`、`quant_sample` | PostgreSQL 5432 | 无 |
| `retrieval_service.py` | `answer`、`interview`、`evidence`、`tag`、`tag_evidence`（pgvector 向量列参与召回） | PostgreSQL 5432（pgvector）、Ollama 11434（`bge-m3:latest` embedding）、Reranker 8082（`/rerank`）、Sparse 8091（`/sparse`） | 无 |
| `insight_service.py` | `quant_sample`、`quant_question` | PostgreSQL 5432 | 无 |
| `segment_aliases.py` | 不建连接；由调用方传入 `conn`，按传入的 `table/field` 读 `DISTINCT` | 无（随调用方） | 无 |
| `joint_service.py` | 不直接建连接，全部委托给 `retrieval` / `quant` / `insight` | 间接依赖上述 PG / Ollama / Reranker / Sparse | 无 |
| `tool.py` | 不直接建连接 | 间接依赖上述服务；另用 Tavily 搜索与 WebFetch | 无（模型在 Agent 侧） |

补充：`retrieval_service` 的 sparse 编码失败会降级为纯 dense，并把降级写入 `warnings`；三个 HTTP 地址是模块常量硬编码，未走环境变量。

### 3.2 文件内相互 import

```
segment_aliases        ← quant_service / retrieval_service / insight_service
quant_service          ← insight_service (DIMENSIONS, _load_env) / joint_service
retrieval_service      ← joint_service
insight_service        ← joint_service（函数内延迟 import）
joint_service          → quant_service / retrieval_service / insight_service
tool.py                → quant_service / retrieval_service / insight_service
```

依赖方向是单向的：`segment_aliases` 是叶子；`joint_service` 与 `tool.py` 位于上层；`insight_service` 依赖 `quant_service` 的维度与配置加载。

## 4. 谁在引用它们

「间接」指该层没有 import，但通过上一层入口在运行时调到。

| 模块 | `agents/` | `app.py` | `tool.py` | `customer_insight/` 内部 | `competitor_insight/` | 测试 / 脚本 |
|---|---|---|---|---|---|---|
| `quant_service` | 间接（经 `tool.py`） | 直接：`/api/insight/quant/options`、`/api/insight/quant/stat` | 直接：`QuantStatService` | `insight_service`、`joint_service` | 无 | `tests/test_choose_reason.py`（`authoritative_label`） |
| `retrieval_service` | 间接（经 `tool.py`） | 直接：`run_interview_evidence_qa`、`run_battle_analysis` | 直接：`InterviewRetrievalService` | `joint_service` | 无 | `tests/test_retrieval.py`、`tests/test_battle.py`、`tests/test_toolkit.py`；`scripts/eval_hybrid_retrieval.py` |
| `insight_service` | 间接（经 `tool.py`） | 直接：`/api/insight/segment/clusters`、`/satisfaction/painpoints`、`/repurchase/intent`、`/matrix/match`、`/compare` | 直接：`InsightService` | `joint_service`（函数内延迟 import） | 无 | `tests/test_insight.py`、`tests/test_choose_reason.py` |
| `segment_aliases` | 无直接 | 无直接（经服务间接） | 无直接（经服务间接） | `quant_service`、`retrieval_service`、`insight_service` | 无 | `tests/test_toolkit.py`（`expand`）、`tests/test_choose_reason.py`（patch `distinct_values`） |
| `joint_service` | 无 | 直接：`/api/insight/joint/analyze`、`/api/insight/cross/validate` | 无 | 无反向引用 | 无 | `tests/test_insight.py` |
| `tool.py` | 直接：`agents/user_insight_agent.py`（`build_user_insight_toolkit`） | 间接：经 `build_business_toolkit` 进入市场战略 / 竞品对标 / 月报链路 | — | `tools/custom_tools.py` 延迟 import `InterviewEvidenceSearchTool` | 无 | `tests/test_toolkit.py` |

`tool.py` 的传播面（通过 `tools/custom_tools.build_business_toolkit()`）：`agents/market_strategy_agent.py`、`agents/benchmark_agent.py`、`utils/monthly_report_narrative.py`、`scripts/run_codex_monthly_research.py`、`scripts/validate_monthly_research_dag.py`。这些调用方只通过该入口取得 `InterviewEvidenceSearchTool`，不使用 `build_user_insight_toolkit()` 内的其余 13 个洞察工具。

## 5. 重点核实：`datasource_service.py` 删除后，竞品洞察是否还 import 底座

核实方法：在 `competitor_insight/` 全目录检索 `customer_insight` 与所有 import 语句，并检查 `web/bci.js` 的后端调用。

- `competitor_insight/` 下唯一的 Python 文件是 `check_board.py`，只 import `re`、`sys`、`pathlib`，**不 import 任何 `customer_insight` 模块**。
- `competitor_insight/web/bci.js` 无 `fetch`、无 `/api/insight/*`、无 `/api/bci/*` 调用；当前只有 `localStorage` 作用域读写。
- `competitor_insight/` 内出现 `customer_insight` 的位置全部是 Markdown 文档（`README.md`、`RULES.md`、`tasks/BCI-001/TASK.md`），不是可执行代码。
- 当前 `app.py` 也没有任何 `/api/bci/*` 路由（旧 `POST /api/bci/datasource/availability` 已随 5×5 实现删除）。

**结论（逐字）：当前竞品洞察对底座零引用，属预留共用。**

## 6. 共用性质判断

| 模块 | 判定 | 依据 |
|---|---|---|
| `segment_aliases` | **真共用（结构底座）** | 三个服务都依赖它的枚举展开，删掉会直接改变空结果行为；虽只被 3 个服务 import，但属于跨服务公共语义层。 |
| `quant_service` | **真共用** | 智能问答工具集与用户洞察页 2 个 API 在用；竞品洞察"按年 + 按群体"的定量分析将来必然要用，但**当前零引用**。 |
| `retrieval_service` | **真共用** | 智能问答的访谈证据问答、战胜战败分析与工具集在用；竞品洞察后续做定性证据洞察时会用到，但**当前零引用**。 |
| `insight_service` | **真共用** | 智能问答 7 个工具与用户洞察页 5 个 API 在用；其中 `competitor_compare` 是现成的横向对比能力，但当前归属用户洞察页，不是为竞品洞察实现的。 |
| `tool.py` | **真共用** | 同时服务两条链路：用户洞察自由问答（14 个工具）与市场战略/竞品对标/月报（仅 `InterviewEvidenceSearchTool`）。 |
| `joint_service` | **实为智能问答专用（被误归入共用）** | 只有 `/api/insight/joint/analyze`、`/api/insight/cross/validate` 和 `tests/test_insight.py` 在引用；`tool.py` 未包装它，竞品洞察也未引用，没有跨线复用证据。 |

补充口径：上表中的"将来必然要用"是需求判断，不是现状。严格按当前 import 证据，竞品洞察与六个文件之间没有任何一条调用关系；`README.md` 与 `RULES.md` 中的"通过 import 引用"目前是约定，尚未发生。

## 附：模块 × 引用方总表（速查）

| 模块 | 直接代码引用方（去重） | 竞品洞察代码引用 |
|---|---|---|
| `segment_aliases.py` | `quant_service`、`retrieval_service`、`insight_service`、`tests/test_toolkit.py`、`tests/test_choose_reason.py` | 无 |
| `quant_service.py` | `insight_service`、`joint_service`、`tool.py`、`app.py`、`tests/test_choose_reason.py` | 无 |
| `retrieval_service.py` | `joint_service`、`tool.py`、`app.py`、`tests/test_retrieval.py`、`tests/test_battle.py`、`tests/test_toolkit.py`、`scripts/eval_hybrid_retrieval.py` | 无 |
| `insight_service.py` | `joint_service`、`tool.py`、`app.py`、`tests/test_insight.py`、`tests/test_choose_reason.py` | 无 |
| `joint_service.py` | `app.py`、`tests/test_insight.py` | 无 |
| `tool.py` | `agents/user_insight_agent.py`、`tools/custom_tools.py`、`tests/test_toolkit.py` | 无 |
