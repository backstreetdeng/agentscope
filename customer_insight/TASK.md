# 用户洞察智能体 · 任务状态（TRAE）

- 主责：TRAE（用户洞察）；Codex 主责市场战略与预测，已有预测功能保持不变。
- 数据基准：`D:\work\AI\用户洞察智能体\方案相关\用户洞察智能体_数据底座_v1_20261030`（2026-10-30 版 manifest / 质量报告）。
- 代码落点：`customer_insight/`（独立业务包，可被 `app.py` 导入）。
- 文档真源：本文件 + `customer_insight/communication/`；不新建平行会话日志。

## 任务总览

| 任务 | 内容 | 状态 |
|---|---|---|
| T0 | 审计复核 + CATARC 借鉴 + 数据/Schema/API 契约核验 | ✅ 阶段性通过（2026-10-30） |
| T1 | 最小开发期 Harness + 文档真源 + 测试入口 + 协作规则 | 🔄 进行中（已授权） |
| T2 | 数据冻结 + 独立 Schema + 导入 | ✅ 完成（2026-10-30） |
| T3 | InterviewRetrievalService + `interview_evidence_search` Tool | ✅ 完成（检索 4 测试通过 + 端到端验证） |
| T4 | 独立同步 API + `reportArea` 证据卡片 | ✅ 完成（API+前端+浏览器端到端验证通过） |
| T5 | 战胜战败决策链专题（群体，车型+能源形式，新增专题 API） | ✅ 完成（API+前端+3测试通过） |
| T6 | 定量问卷统计与群体差异（导入 DB + 前端看板 + 全部维度） | ✅ 完成（导入1380样本+看板验证通过） |
| T7 | 配置建议及联合洞察（三颗粒度，专题报告+结构化看板） | ✅ 完成（联合洞察API+前端验证通过） |
| T8 | SSE/Checkpoint/运行期Harness增强 | ⏸ 待定 |

## T1 目标

建立最小开发期 Harness、文档真源、测试验证入口和协作规则。

## T1 范围与禁止项

- 范围：`customer_insight/` 包骨架、任务真源（本文件）、`tests/` + Windows 校验入口（stdlib unittest）、协作规则。
- 禁止：重构业务代码、执行生产数据库迁移、修改市场战略及预测功能、触碰 `app.py` 及预测相关未提交修改。

## T1 待办

- [x] 检查现有模块是否已有等价功能（避免重复建设）——复用 `ReadOnlyBusinessTool`、`SkillRunContext`、`tests/`(unittest)、`scripts/` 既有约定；无 `services/`、无访谈检索等价实现。
- [x] 建立 `customer_insight/` Python 包骨架（`__init__.py`，`__version__=0.1.0`）。
- [x] 建立 `customer_insight/tests/test_smoke.py` 与 `verify.ps1` 校验入口（stdlib unittest，2 例通过）。
- [x] 确定文档真源唯一（`reference_docs/02_工程事实依据` 为 SSOT，README 已建，SHA256 核对与数据底座 `03_实现设计` 一致；2026-10-30 定稿）。
- [ ] Git 分支/worktree：约定已写入；实际分支未创建（T4 已在当前 checkout 的 main 上最小修改共享文件，未提交、未建分支、未推送）。

## T1 验收标准

- 非用户洞察模块零意外变更；市场/预测回归基线通过。
- 测试入口可运行（单元测试用合成数据，不称真实业务验收）。
- 文档真源唯一，不产生平行清单。

## 已确认的环境事实（2026-10-30）

- 目标数据库：`192.168.3.146:5432` 的 `vectordb` 库（市场数据与用户洞察目标库同一实例）。
  - 运行期查询账户：`market_mcp_reader`（只读，经环境变量 `MARKET_PG_*` / `NEW_CAR_PG_*` 注入）。
  - 旧 rag-engine 的 `vectordb`/`vectordb123` 是独立工程的硬编码写账号，存在安全隐患，用户洞察不沿用。
- Embedding：服务器 Ollama `bge-m3:latest` @ `192.168.3.146:11434`（1024 维，与 `vector(1024)` 兼容）；已探活（2026-10-30），`/api/embed` 返回 1024 维。
- Reranker：`http://192.168.3.146:8082`（FastAPI）；已探活（2026-10-30），`/health` 200、`/rerank` 端点存在。均内网 HTTP 直连，无需 SSH 隧道。
- SSH 连接 146 已核验（2026-10-30 probe）：Paramiko 5.0.0 已装至 `%LOCALAPPDATA%\Codex\ssh-146\python-packages`，凭据 `C:\deng\.env` 就绪；probe 返回 `target_verified`（root / ubuntu-virtual-machine / 192.168.3.146:12816）与 `probe_succeeded`，`normal_logout=true`。
- `user_insight` schema 已创建（2026-10-30）：在 146 `vectordb` 库执行完整 Schema SQL，7 张表（interview/question/answer/evidence/tag/tag_evidence/retrieval_run）+ 索引，全部 `IF NOT EXISTS` 幂等；DDL 账户 `vectordb`（一次性），未触碰 public/policy_monitor/policycrawlerdb/staging。

## 协作边界（Codex 已确认 2026-10-30）

- `app.py` + 6 个已跟踪文件的未提交修改 = 现有预测工作与交接记录，TRAE 完整保留，不覆盖、不回退；未跟踪预测源码/测试/依赖一并保留。
- T4 须待 T3 完成并取得授权。共享文件最小修改：
  - `app.py` 仅新增独立访谈查询路由及必要调用，保留现有预测、聊天、报告接口。
  - `legacy_workbench.html` 仅在用户洞察结果区增加证据卡片。
  - `model_config/config.json`、`.env.example` 默认不改，确有需求时只追加独立配置或无真实凭据示例。
- 实施前：核对最新 Git 状态，先形成含未跟踪预测源码的可复现基线，再协调分支/Worktree，回归原有接口、预测功能与页面。

## T2 前置（进入 T2 前必须明确）

- Schema 结构已建（2026-10-30，`user_insight` + 7 表 + 索引，见上文）；数据导入账户已建 `user_insight_loader`（独立写账户，非超户，密码存 `.env`，经 SSH→postgres 创建）；查询账户 `market_mcp_reader` 只读；回滚 = `DROP SCHEMA user_insight CASCADE` / `DROP ROLE user_insight_loader`（需授权）。
- 口径已核验（2026-10-30）：标签=5355（非 45,244，45,244 是标签证据数）；`tag_evidence.csv` 45244 行 `tag_id` 全部有效（unmatched=0），结构化数据已解决 29 条未关联，无 `NOT NULL` 冲突。
- `retrieval_run` PII 保留策略已定（见 `reference_docs/02_工程事实依据/用户洞察智能体_运行数据保留策略_20261030.md`），T2 落实 Schema 改动与自动清理。
- Embedding / Reranker 只读接入方式已探活（内网 HTTP 直连，见上文），待 T3 接入检索服务。

## T2 执行记录（2026-10-30）

- 数据冻结：口径以 `00_manifest` + `data_quality_report.md` 为权威；字段映射与转换规则见 `temp/20261030-freeze-inventory/manifest.json`。
- 数据导入：`ops/import_user_insight.py` 按外键依赖导入 6 表，全部 `ON CONFLICT DO NOTHING` 幂等。
  - 结果行数：question=85、interview=63、answer=5355、evidence=81437、tag=5355、tag_evidence=45244（均匹配权威口径）。
  - 字段转换：`mapped_question_ids` `'Q68'`→`[68]`；`time_available` `'False'`→bool；JSON 字符串→jsonb；空 `start_sec/end_sec`→NULL。
- Embedding：`ops/backfill_embedding.py` 为 answer（answer_text）与 tag（`tag_name: tag_value`）补 bge-m3 1024 维向量，幂等（仅 `embedding IS NULL`）；已完成（answer=5355、tag=5355 全部有向量）。
- 回滚：`DROP SCHEMA user_insight CASCADE;` + `DROP ROLE user_insight_loader;`（均需授权）。

## T3/T4 执行记录（2026-10-30）

- T3 检索服务：`customer_insight/retrieval_service.py`（`InterviewRetrievalService`）
  - 白名单过滤（city/vehicle_model/purchase_type/question_ids/tag_names/tag_values/respondent_codes）→ 向量召回（pgvector 余弦 top 30）→ Reranker top_k → 证据打包（E1..En，同受访者限量，最多 8 条）。
  - 测试：`customer_insight/tests/test_retrieval.py` 4 例通过；端到端验证（检索 + Agent 归纳）通过，证据不足时正确拒答不编造。
- T3 Tool：`customer_insight/tool.py`（`InterviewEvidenceSearchTool`，继承 `ReadOnlyBusinessTool`），已加入 `build_business_toolkit`。
- T4 API：`app.py` 新增 `POST /api/insight/interview/query`（`run_interview_evidence_qa`），确定性检索 → 证据注入 → Agent 归纳 → [E#] 引用校验。
- T4 前端：首页 `home.html` 的 `#insight` 板块新增「访谈证据问答」区块 + 证据卡片渲染（`assets/home.js` 的 `InsightQA` 模块）。
- 代码落点（2026-11-01 迁移）：用户洞察核心业务逻辑集中到 `customer_insight/` 包内——`retrieval_service.py`（检索服务）、`tool.py`（AgentScope Tool）；仅保留共有资源在外层（`tools/custom_tools.py` 的 `ReadOnlyBusinessTool` 基类、`agents/user_insight_agent.py`、`ops/` 导入脚本、`app.py` 的 Web 层）。已删除 `services/` 目录。
- 前端（2026-11-01 迁移）：证据问答从废弃的 `legacy_workbench.html` 迁到首页 `home.html` 的 `#insight` 板块（`assets/home.js` 的 `InsightQA` 模块 + `assets/home.css` 样式），删除静态「用户洞察 · Demo 演示」。
- 浏览器端到端验证已通过（2026-11-01，用户已授权启动服务）：选「访谈证据问答」→ 提问 → 6 条 evidence-card 渲染、无未捕获 JS 报错。
- 待办：查询账户 `market_mcp_reader` 凭据未配置（当前检索复用 `user_insight_loader`，后续应切独立只读账户）。

## T5 战胜战败决策链专题（进行中，2026-11-01 已授权）

### 目标
基于访谈证据做群体战胜战败结构化归因：对比了哪些车型 → 战胜/放弃了哪些（及原因）→ 能源形式取舍，逐条挂证据引用，不强行因果推断。

### 数据基础
标签 `content_group`：对比车型(126)、选购原因(126)、弃购原因(63)、能源偏好(567)；对应 Q26/Q29/Q27-28/Q10-19。

### 已确认决策
- 粒度：群体（面向目标车型/圈层整体）
- 交付：新增专题 API `POST /api/insight/battle/analyze`
- 维度：车型对比战败 + 能源形式战败

### 落地步骤
- [x] T5-1 检索服务新增 `battle_search`（按 vehicle_model + content_group 检索标签与证据，结构化聚合）
- [x] T5-2 新增 API `POST /api/insight/battle/analyze`（确定性检索 → 结构化归因 → Agent 归纳 → 引用校验）
- [x] T5-3 前端 `#insight` 板块加战胜战败分析入口
- [x] T5-4 测试 + 验收（`test_battle.py` 3 例通过 + API 端到端 + 浏览器验证）

### 验收结果
- `battle_search`：唐L 3 位受访者，返回对比车型/选购原因/弃购原因/能源偏好四维度结构化归因，证据带 [E#] 引用。
- API 端到端：`POST /api/insight/battle/analyze` 返回完整战胜战败决策链归纳（对比车型/放弃原因/选购原因/能源取舍），引用 [E#] 合法。
- 前端浏览器验证：4 个维度标题 + 6 张证据卡片渲染，无未捕获 JS 报错。
- 不强行因果推断：只陈述受访者原话归因，证据不足时无证据不编造。

### 验收标准
- 输入目标车型，返回对比车型/弃购原因/选购原因/能源取舍的结构化归因
- 每条归因有证据引用（[E#] 指向真实 evidence），不强行因果推断，无数据不编造

## T6 定量问卷统计与群体差异（进行中，2026-11-01 已授权）

### 目标
导入定量数据（1380×1324），按群体维度统计问卷字段分布，前端看板展示群体差异。

### 数据基础
- `2025定量数据汇总.xlsx`（数字版+中文版，各 1380 行 1324 列，前 2 列无表头）
- `quant_columns.csv`（1324 字段映射：column_index → header/question_prefix）
- `quant_respondent_index.csv`（1380 样本群体维度：车型/购车类型/价格段/城市/年龄段/性别）

### 已确认决策
- 数据方式：导入数据库（建定量 schema）
- 交付：前端看板（#insight 板块）
- 维度：全部（购车类型/价格段/年龄段/性别/城市/车型）

### 落地步骤
- [x] T6-1 建定量 schema（quant_sample + quant_question）+ 导入 1380×1324 数据（经 SSH 补 loader CREATE 权限）
- [x] T6-2 统计服务 `customer_insight/quant_service.py`（QuantStatService：按维度分组统计某题分布）
- [x] T6-3 前端看板（#insight 板块：维度下拉 + 题目下拉 + 分布条形图）
- [x] T6-4 测试 + 验收

### 验收结果
- 定量数据导入：quant_sample=1380 行、quant_question=1283 题（数字版+中文版 answers 存 jsonb）。
- 统计服务：按 6 个维度（购车类型/价格段/年龄段/性别/城市/车型）分组统计，分母透明（sample_count 与 profile 口径一致）。
- 前端看板浏览器验证：6 维度 + 200 题目下拉填充、分布表格渲染、样本数自洽，无未捕获 JS 报错。
- 数据边界：定性标签与定量比例分离（不同表、不同统计口径），不混用。

### 验收标准
- 定量数据完整导入（1380 样本，数字版+中文版）
- 按群体维度统计某题分布，分母透明
- 定性标签不能换算成定量比例（数据边界）

## T7 配置建议及联合洞察（进行中，2026-11-01 已授权）

### 目标
综合定性证据 + 战胜战败 + 定量统计，输出配置优先级建议（专题报告 + 结构化看板）。

### 已确认决策
- 颗粒度：目标车型 / 用户圈层 / 购车类型（三种都要）
- 输出：专题报告（Agent 归纳）+ 结构化看板（分区块展示）

### 落地步骤
- [x] T7-1 联合洞察服务 `joint_insight`（聚合定性证据 + 战胜战败 + 定量统计，quant_service 加 stat_in_group）
- [x] T7-2 API `POST /api/insight/joint/analyze`
- [x] T7-3 前端联合洞察入口（三颗粒度下拉 + 专题报告 + 结构化摘要 + 证据卡片）
- [x] T7-4 测试 + 验收

### 验收结果
- 联合洞察服务：`joint_insight` 聚合三个既有能力，支持 vehicle_model/purchase_type/age_band 三颗粒度。
- API 端到端：唐L → 5 条配置建议（续航版本/四驱/空间内饰/插混信任/智驾证据不足），标注"样本结果非普遍结论"。
- 前端浏览器验证：三颗粒度下拉 + 专题报告 + joint-meta（定性6/战胜战败3/定量13）+ 6 张证据卡片，无 JS 报错。
- 数据边界：结论区分样本结果与研究假设，智驾证据不足时不强行列为高优先级。

### 验收标准
- 三种颗粒度都能分析（车型/圈层/购车类型）
- 专题报告带证据引用，结构化看板分区块展示
- 结论区分样本结果与研究假设，不混用定性/定量口径

## 洞察能力扩展（已完成，2026-11-01 用户授权）

复用现有 retrieval/quant/joint 三件套，套到更多业务问题。按业务价值排序：

| # | 能力 | 状态 |
|---|---|---|
| 1 | 圈层画像聚类（真实聚类替代首页静态圈层） | ✅ 完成（commit b1902cb） |
| 2 | 满意度痛点洞察（某车型/圈层最不满意的 Top 点 + 原声） | ✅ 完成（commit 143e1a7） |
| 3 | 再购意愿与品牌忠诚（谁会流失、为什么） | ✅ 完成（commit 5a36cd6） |
| 4 | 需求×配置匹配矩阵（真实数据生成） | ✅ 完成（commit 11cd5d7） |
| 5 | 竞品横向对比（跨车型配置关注差异） | ✅ 完成（commit c76c314） |
| 6 | 圈层差异交叉验证（定性原声 + 定量分布并排） | ✅ 完成（commit f2ebd2b） |

验收：每个能力有服务 + API + 前端 + 测试，遵守不编造/区分样本与假设/定性定量分离。

### 实现要点（2026-11-01）

- 满意度 Q5_2__1~16 为 10 分制打分，痛点口径 = 打分 ≤6 的低分率 + 均分；购车关注因素 Q3_23__1~16 为勾选（1=勾选），16 维度一一对应。
- 再购题号核验：再购时间 Q6_3、再购技术类型（燃料）Q6_4、再购意向品牌 Q6_5、品牌忠诚（是否同品牌）Q2_7（非原假设的 Q6_2/Q6_3）。
- 服务落点：`insight_service.py`（satisfaction_painpoints / repurchase_intent / demand_config_matrix / competitor_compare）、`joint_service.py`（cross_validation）。
- API：`/api/insight/satisfaction/painpoints`、`/api/insight/repurchase/intent`、`/api/insight/matrix/match`、`/api/insight/compare`、`/api/insight/cross/validate`（均同步，已加入 do_POST 白名单，commit d63159c）。
- 前端：`#insight` 板块新增 5 个区块（满意度痛点/再购意愿/需求×配置矩阵/竞品横向对比/圈层交叉验证）。
- 测试：`customer_insight/tests/test_insight.py` 11 例通过（含 #6 定性检索，Ollama/reranker 在线）；5 个 API 端到端验证通过（唐L：痛点 Top=纯电续航里程、矩阵 16 维度四象限、交叉验证定性 4 条+定量 16 维度）。
- 数据边界：定性原声与定量比例并排但不混用口径；四象限按群体内中位数划分，标注样本结果非普遍结论。

