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
- 证据选段修复（2026-11-02）：同一 answer 由「按时间取第一条」改为按与 `answer_text` 的字符二元组重叠评分取 2 段，问句/题干片段降权（`MAX_EVIDENCE_PER_ANSWER=2`）。「计划换车」复验返回受访者真实回答（R035 四五年换代、R040 3~4 年还贷、R058 七八年）；`test_retrieval` 4 例通过。
- 布局与说明书（2026-11-02）：`#insight` 四 Tab 改为「1 检索问答 → 2 定量统计 → 3 专题洞察 → 4 对比与验证」四步链路；战胜战败从检索问答移入专题洞察；10 个功能全部加卡片标题与一句话说明；新增 Tab 使用引导与头部描述。`customer_insight/使用说明.md` 重写为完整操作手册（四 Tab 关系、10 功能步骤/示例/输出解读、群体取值速查）。
- 待办：查询账户 `market_mcp_reader` 凭据未配置（当前检索复用 `user_insight_loader`，后续应切独立只读账户）。
- 服务重启（2026-11-02，用户授权）：重启 7860 后已确认新页面生效（10 张 `insight-card`、引导条、战胜战败归入专题洞察、无旧 `qa` 归属）；启动脚本的隐藏进程未存活，改用后台常驻方式启动。
- Tab 筛选缺陷修复 + 复验（2026-11-02）：`initTabs()` 选择器依赖 `#insight` 容器，但 `<section class='insight'>` 缺该 id，导致 `blocks` 为空、10 张卡片始终全部可见。已补 `<section id='insight'>` 并新增 `.insight-card[hidden]{display:none!important}`。重启后浏览器实测：默认仅 1 张（访谈证据检索）、定量统计 1 张、专题洞察 5 张、对比与验证 3 张，`aria-selected` 正确迁移、无 JS 控制台报错。
- Sparse 向量回填（2026-11-02，用户授权）：为 `user_insight.answer` 新增 `sparse_embedding sparsevec(250002)` 列并回填全部 5355 条 bge-m3 稀疏向量（lexical weights）。实现路径：复用 146 `torchai` conda 环境已装的 `FlagEmbedding 1.3.5` + `torch 2.6`（CPU 推理，`use_fp16=False, device='cpu'`），经国内 `hf-mirror.com` 下载 `BAAI/bge-m3` 权重（4.3G，snapshot `5617a9f`）；`sudo -u postgres` 走 peer 认证免密连库，凭据不落盘不传远端。转换规则：bge-m3 词表 250002，lexical_weights 的 token_id（0-based，key 为 str）→ sparsevec 下标 `token_id+1`（1-based）。回填结果：`count(*)=5355`，`count(sparse_embedding)=5355`，全部命中；样例行 `A-R001-Q001` 读回值格式 `{5:0.0425,...,227838:0.215}/250002` 正确。生成耗时约 66s（CPU）。命令文件落 `ops/20261102-sparse-*.sh`（环境检查/下载/生成/导入/校验）。**检索链路尚未接入 sparse**（`retrieval_service.py` 仍为纯 dense+rerank），待用户确认是否做 dense+sparse 混合检索。
- Dense+Sparse 混合检索 + 评测（2026-11-02，用户授权）：已接入。① 146 部署常驻 sparse 编码服务 `sparse_server.py`（FastAPI + FlagEmbedding，`torchai` 环境，CPU，端口 8091，`POST /sparse` 返回 `[[token_id, weight], ...]`）。② `retrieval_service.py` 新增 `_embed_sparse`/`_sparse_vec_str`/`_rrf_fuse`，`search()` 改为 dense 余弦（`<=>`）+ sparse 负内积（`<#>`）各召回 top30 → RRF(k=60) 融合 → rerank → 证据打包；sparse 服务故障自动降级纯 dense（`matched_by` 标注 `hybrid+rerank`/`vector+rerank`）。③ 评测集 `scripts/eval_hybrid_retrieval.py`：10 个 query，用 tag 语义标注（content_group + tag_value 模式 → 关联 answer）作 ground truth，指标 Recall@10/30 + MRR。**评测结果：MRR 0.452→0.523（+15.7%，排序改善明显），Recall@30 0.151→0.160（+6%，召回基本持平）**；部分 query（续航焦虑/使用成本/纯电续航）hybrid 反而略降。结论：小语料（5355 条）+ 已有 cross-encoder reranker 下，sparse 融合的收益主要在排序（MRR）而非扩展召回（Recall）；语义类 query 是 dense 强项，sparse 主要补专有名词（800V/NOA 等）精确匹配。

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

## agentic 自由问答改造（2026-11-02 已授权）

把用户洞察从「确定性 RAG（预编排检索 → 注入 → 归纳）」升级为「agentic RAG（Agent 自主决定调用哪个工具）」，原确定性端点保持不变、不被替换。

### 落地（A→D）

- A 工具化：`customer_insight/tool.py` 新增 `battle_search` + quant(3：list_questions/stat/stat_in_group) + insight(5：圈层/痛点/再购/矩阵/竞品) 共 9 个 `ReadOnlyBusinessTool`；`build_user_insight_toolkit()` 返回 10 个洞察工具（独立于市场战略共用 toolkit，不污染）。
- B Agent 引导：`agents/user_insight_agent.py` 新增 `USER_INSIGHT_FREE_QA_PROMPT`（列工具 + 使用规则 + [E#] 引用 + 证据不足拒答 + 定性定量分离）+ `build_user_insight_free_qa_agent()`（带工具 ReAct，max_iters≥8）。
- C agentic 端点：`app.py` 新增 `POST /api/insight/agent/query`（已入 do_POST 白名单），`run_insight_agent_query()` 返回 answer + evidence + tool_events + warnings。
- D 反幻觉硬门：`tools/custom_tools.py` 新增全局证据注册表 `register_evidence / clear_evidence_registry / get_collected_evidence`；工具跨轮全局编号，请求结束统一 [E#] 引用校验，证据不足时拒答不编造。

### 验证

- 语法编译通过；`customer_insight/tests/test_toolkit.py` 4 例通过（工具集 + 全局编号注册 + 清空）。
- 端到端（真实 DeepSeek + 内网 PG/Ollama/reranker）：问「唐L 用户最不满意哪些方面」→ Agent 自主调用 `satisfaction_painpoints` + `interview_evidence_search`，正确区分定量/定性、[E#] 引用合法、访谈证据不足时明确拒答不编造、样本量 n=44 不推断普遍性。
- 原确定性端点（`/api/insight/interview/query` 等）未改动，行为不变。

### 前端接入（2026-11-02）

- `home.html`：新增「智能问答」Tab（默认选中，`data-insight-tab='agent'`）+ 输入卡片；引导文案改为「一句话问到底用智能问答，分步用四步链路」。
- `assets/home.js`：新增 `renderMarkdown`（轻量 markdown：标题/表格/列表/加粗）、`renderToolEvents`（工具调用审计）、`askAgent`（fetch `/api/insight/agent/query`）；`initTabs` 默认 `agent`，`init` 绑定事件。
- `assets/home.css`：新增 `md-table/md-h/md-p/md-li/tool-event` 样式。

### 浏览器端到端验证（2026-11-02）

- 已重启 7860 加载新代码（新端点 `/api/insight/agent/query` 空参数返回 400 验证通过）。
- 浏览器实测 `#insight`：「智能问答」Tab 默认选中；输入「唐L用户最不满意哪些方面？」→ 返回 markdown 答案 + 证据卡 + 工具调用列表（`satisfaction_painpoints` / `interview_evidence_search` ×2 / `demand_config_matrix` 共 4 条 success），无 JS 报错。

### 流式思考过程（2026-11-02 追加）

- 问题：答案一次性返回，用户看不到 Agent 的决策过程（调了哪些工具、推理了什么）。
- 方案：新增 `POST /api/insight/agent/stream`，用 AgentScope 2.0.3 `Agent.reply_stream()` 把事件实时推送为 NDJSON（`application/x-ndjson`，无 Content-Length，逐行 flush）。
  - 事件：`start` / `round` / `reasoning_start|delta|end` / `tool_start` / `tool_result` / `final` / `error`。
  - 最终答案取**最后一个文本块**；前置文本块是 ReAct 推理过程，仅用于实时展示。`[E#]` 硬校验逻辑与非流式端点一致（跨轮 `valid_ids`）。
- 前端：`askAgent()` 改为 `fetch` + `ReadableStream` 逐行解析 NDJSON，实时渲染「思考过程」时间线（推理文本带流式光标、工具调用步骤带 进行中/完成 状态），结束后渲染答案 + 证据 + 工具审计。
- 缓存：`home.html` 的 `home.css` / `home.js` 加 `?v=20261102`，避免浏览器沿用旧 JS 仍请求 `/agent/query`。
- 验证：
  - 直调 `stream_insight_agent_query`：`round=6, reasoning_delta=1292, tool_start=12, final=1`，答案 1760 字、证据 8 条、工具 12 条、无 warning。
  - HTTP 实测（Python 客户端）：`content-type=application/x-ndjson`，首个事件 0.04s 到达，端到端 2.3s（简单问题）。
  - 浏览器实测：点击后 **0.56s** 出现「思考过程 实时」，`agent-think`/`agent-step` 计数持续增长（1/2→5/10），结束时显示「已完成 · 10 次工具调用」，答案 4846 字符。

### 多轮对话与联网补数（2026-11-02 追加）

- 问题：单轮问答，用户追问「那你直接去查这些车型的续航差值」时无法延续上文；且 Agent 没有联网工具，续航等外部事实查不到。
- 多轮：
  - `customer_insight/session.py` 内存会话（`get_history / append_turn / reset`，保留最近 6 轮，TTL 1 小时）。后续要持久化只需替换这三个函数。
  - `build_insight_conversation_inputs()` 把历史拼成 `UserMsg/AssistantMsg` 列表，连同新问题一起传给 `reply_stream`。
  - `start` 事件带 `history_turns`；前端在思考过程头部显示「已带 N 轮上文」。
  - `[E#]` 校验仍按**本轮**证据集合，保证编号与当轮证据卡一一对应。
- 联网：
  - `customer_insight/tool.py` 新增 `web_search`（Tavily）与 `web_fetch`（公开网页正文），Toolkit 从 10 个增至 12 个。
  - 系统提示新增规则：访谈/问卷未覆盖的外部事实（续航、价差、配置）主动联网查，必须标注来源 URL 与「公开网络信息，需业务复核」，不得与访谈原话/问卷比例混用。
  - `max_iters` 提升至 ≥12。
- 前端：`#insight-agent-thread` 对话线程（用户气泡 + 每轮思考过程 + 答案 + 证据 + 工具审计），新增「清空对话」，会话 id 存 `sessionStorage`。
- 表格溢出修复：markdown 表格包进 `.md-table-wrap`（`overflow-x:auto`），避免宽表把输入栏挤出屏幕。
- 验证：
  - 直调两轮：第 1 轮 8 次工具调用命中 4 位因续航弃购受访者；第 2 轮 `history_turns=1`，自主调用 `web_search` 4 次，输出「用户自述续航 vs 官方 CLTC」对照与差值，并标注来源 URL。
  - 浏览器实测：两轮问答并存于同一线程；第 2 轮头部显示「已带 1 轮上文」，工具步骤 3 次 `web_search`，答案含官方 CLTC 参数、差值与 xinhuanet/xiaopeng 等来源链接；「清空对话」后线程清空且 `sessionStorage` 移除。

### 四象限规则修复（2026-11-02 追加）

- 问题：需求×配置矩阵用「群体内相对中位数」划分四象限，导致同一个「高关注·低不满」维度跨群体分类漂移。实例：舒适性（关注 47.6%、低分率 3.6%、均分 8.6）在增购组被误判「优先改进」，在换购组却是「核心优势」。
- 根因：`demand_config_matrix` 用本群体关注度/低分率中位数作为阈值，非固定业务阈值。
- 修复：
  - 改为固定阈值（跨群体一致）：关注度 ≥ 25%（约全样本中位数），低分率 ≥ 5.7%（全样本 P75，n=1380、16 维度，2026-11-02 计算）。
  - 四象限标签按业务语义重命名：优先诊断（高关注·高不满）/ 重点维持（高关注·低不满）/ 局部痛点（低关注·高不满）/ 保持监测（低关注·低不满）。
  - 返回字段 `att_median`/`low_median` 改为 `attention_threshold`/`low_rate_threshold`（语义准确，无消费方）。
  - 补 n=0 边界：群体取值匹配不到时返回空 items，不再全量误判「优先改进」。
- 同步：`home.js` renderMatrix 新象限名 + 颜色 + 阈值口径说明；`tool.py` 工具描述；`test_insight.py` 断言。
- 验证：增购组舒适性由「优先改进」修正为「重点维持」；换购组同样归「重点维持」，规则跨群体一致。`TestDemandConfigMatrix` 2 例通过。

### 信息架构重构：主入口 + 证据抽屉（2026-11-02 追加）

- 问题：原 `#insight` 用 5 个并列 Tab（智能问答/检索问答/定量统计/专题洞察/对比验证），把工具当功能并列展示。用户不清楚「检索问答」和「智能问答」区别，也不知道后三个该什么时候用；且各卡片的群体取值只能手输，上一轮问答涉及的群体条件不会带到下一张卡片。
- 方案：对外只保留「智能问答」一个主入口，其余工具收进 4 个默认收起的证据抽屉：
  1. 原话来源 · 访谈检索（标注内部工具，智能问答已自动调用）
  2. 比例来源 · 定量统计
  3. 固定口径 · 专题洞察（战胜战败/圈层/痛点/再购/矩阵/联合洞察）
  4. 一致性 · 对比与验证（竞品横向对比/圈层交叉验证）
- 参数继承：新增 `#insight-ctx` 上下文条。`final` 事件里解析 `tool_events[].detail`（`group=<维度>=<取值>`、`filter=<维度>=<取值>`），自动写入定量维度、痛点/再购/矩阵/交叉的维度+取值、联合洞察颗粒度、战胜战败车型；手动点击任一分析按钮也会反向同步上下文，一处改动处处一致。
- 文件：`home.html`（#insight 区块重排，CRLF 统一）、`assets/home.js`（`initDrawers` / `applyContext` / `inheritFromToolEvents`，移除 `initTabs`）、`assets/home.css`（`.insight-ctx` / `.insight-drawer*` 样式，移除 tab 样式）。
- 验证（Chrome headless 真实浏览器，拦截流式接口注入 `filter=purchase_model=唐L` 事件）：16/16 通过——无编号 Tab、主入口唯一、4 抽屉默认收起、抽屉可展开、上下文条显示「车型 = 唐L / 来自本轮工具调用」、痛点/再购/矩阵/交叉/联合/战胜战败 6 个输入框全部自动填入唐L、维度下拉同步 `purchase_model`、联合颗粒度同步 `vehicle_model`、定量题目仍加载 1283 条、无 JS 报错。截图 `outputs/20261102-insight-refactor/insight-drawer.png`。
- 另用真实模型跑通一次「唐L用户最不满意哪些方面？」：6 次工具调用完成，上下文条显示「车型 = 唐L / 来自本轮工具调用」。

### 购车关注题号修复（2026-11-02 追加）

- 问题：`insight_service.ATT_PREFIX` 原为 `Q3_23__`，注释写"购车关注因素"，但 Q3_23 实际是「选择最终购买车型的原因」（战胜原因），不是购车关注因素。真正的购车关注因素是 Q3_13。
- 根因：H1→H2 题号迁移——H1 3.11 购车关注 → H2 `Q3_13`；H1 3.15 选择最终车型原因 → H2 `Q3_23`。代码把战胜原因题（Q3_23）错当成购车关注题。
- 证据：`quant_columns.csv`（col 295-310=Q3_13 购车关注，col 651-666=Q3_23 选择最终车型原因，两者 16 维度标签相同但语义不同）。
- 修复：
  - `ATT_PREFIX` 由 `Q3_23__` 改为 `Q3_13__`（购车关注因素）。
  - 新增 `CHOOSE_REASON_PREFIX = "Q3_23__"`（选择最终车型原因，独立指标，勿与购车关注混用）。
  - `joint_service.CONFIG_QUANT_QID` 由 `Q3_23__14` 改为 `Q3_13__14`。
  - `quant_service`、`tool.py` 注释/示例同步修正。
- 影响：`demand_config_matrix`、`competitor_compare` 的"关注度"从战胜原因数据回归到购车关注数据。增购舒适性关注度由 47.6%（Q3_23）修正为 43.6%（Q3_13），与 Agent 自由问答口径一致。
- 验证：`TestDemandConfigMatrix` 2 例通过；`repro_quadrant.py` 复验增购/换购四象限数据语义正确（舒适性→重点维持、续航/智驾→优先诊断）。

### 待办

- 查询账户仍复用 `user_insight_loader`，未切独立只读账户 `market_mcp_reader`。
- 改造后代码未提交（仅基线 `fd177df` 已本地 commit），待用户确认后再提交。

## 诊断报告问题修复（2026-11-03）

第一项交付物《智能问答诊断报告（8 个问题实测）》的修复闭环，逐项对应报告编号：

- [x] 1.2 聚合词静默空结果：新增 `customer_insight/segment_aliases.py`（读库真实枚举 + 5 分钟缓存 + 聚合词展开）；`demand_config_matrix` / `stat_in_group` / `search` / `battle_search` 精确匹配改 `= ANY(%s)`，正常结果回传 `expanded_values`，空结果回传 `available_values` + `hint`。
- [x] 1.3 访谈员提问混入引文：`_clean_quote` 去前缀、按最后一个问号切「提问+回答」、截断「……，您……」追加追问；`_looks_like_question` 增加无问号复述式追问识别；`_pick_evidence_segments` 改提问硬过滤。
- [x] 1.8 具体配置下钻：`InsightService.config_detail` + 工具 `config_detail`，Q3_13_1__NN 明细项按群体勾选率返回（库内实际 94 项，原文档写的 117 已修正）。
- [x] 1.7 关注/满意/战胜口径混用：`USER_INSIGHT_FREE_QA_PROMPT` 规则 7/11 明确 Q3_13 / Q5_2 / Q3_23 / Q3_24_1 不可互推，因果表述必须有 battle_search 证据。
- [x] 1.1 关键词试错题号：工具描述写明题号语义与下钻路径，提示词补题号字典与排他表述核对（规则 9）。
- 1.4 / 1.5 / 1.6 为前序修复，本次复跑未回退（增购舒适性 43.6% 来自 Q3_13，非 Q3_23）。

验证：
- `temp/20261103-insight-audit/verify_fixes.py`：10 项断言 PASS（矩阵 n=547 / group_size=547 / 定性 evidence 非空 / 引文无提问残留 / 明细层口径一致）。
- `temp/20261103-insight-audit/verify_quotes.py`：同一 query 6 条证据逐条无问号、无“您”、无访谈员前缀。
- 端到端「增换购用户最看重哪些配置？」（新会话）：3 次工具调用 `config_detail` → `demand_config_matrix` → `interview_evidence_search`，无关键词试错；答案分层（16 维度 / 94 配置项）并注明展开口径。日志 `temp/20261103-insight-audit/e2e_v2.log`。
- 端到端复验（排他表述）：修复后只调用 `config_detail` + `demand_config_matrix` 即完成两层结论，四象限写“优先诊断共 2 项：纯电续航里程、智能驾驶”，不再出现“唯一”。日志 `temp/20261103-insight-audit/e2e_v4.log`。
- 单测：`python -m unittest discover -s customer_insight\tests` 27 例通过（`test_toolkit` 工具数更新为 13，新增 `TestSegmentAliases` 3 例）。
- 未提交 Git；未重启 7860 服务（遵守月报浏览器保护规则，验证走独立进程）。

### 1.3 残留缺陷（2026-11-03 浏览器自测发现并修复）

浏览器实测「唐L用户最不满意哪些方面？」时，证据列表出现访谈员复述「明白，好的。也就是说回来看了看插混这样的，你买四驱主要考虑到SUV动力性。」，说明 1.3 只修了带问号和「您」的情形。

- 根因一：`_looks_like_question` 只看清洗后文本，`M：` 前缀已被 `_clean_quote` 剥掉，最可靠的访谈员信号丢失。
- 根因二：`_pick_evidence_segments` 用 `positives or non_questions`，与答案相似度高的访谈员发言会绕过提问过滤回到证据池。

修复：
- 新增 `_INTERVIEWER_PREFIX`，`_looks_like_question` 在清洗前先判 `M/Q/问/访/主持人/访谈员` 前缀。
- 证据池改为 `[item for item in non_questions if item[0] > 0] or non_questions`，提问永不进入。
- 曾试加「也就是说/就是说」为问句线索，测出会误杀受访者原话（如「主要就是说。」），已回退，只保留前缀判定。

验证：
- `temp/20261103-insight-audit/verify_leak_v2.py`：全库 81437 条证据，带访谈员前缀 1389 条 100% 判为提问；唐L 检索 8 条证据全部 OK。
- 浏览器复测（服务重启后新会话）：回答 4106 字，15 条证据全为受访者原话，旧句消失，无 `M：`/「您觉得」/「也就是说」痕迹。
- `test_toolkit` 7 例通过。

遗留（2026-11-03 记录）：无前缀受访者侧约 21.9% 被问句线索误过滤（如「感觉也不怎么样」）——只影响召回不影响正确性的旧表述被用户否定（召回损失即间接影响结果正确性），2026-11-04 修复见下节。

## 前端口径与召回优化（2026-11-04）

用户验收反馈两项修复（唐L 口碑库无数据由用户安排旧电脑采集，不在本任务范围）：

### 工具调用清单口径一致（思考过程 5 次 vs 底部清单 3 条）

- 现象：思考过程按框架 `tool_call_start` 流式事件计数（含 MCP 口碑工具），底部「工具调用」清单来自 `record_tool_call` 审计日志，而 MCP 工具（`mcp__reputation_data_mcp__*`）由框架直接调用、不经任何包装，从不写入审计日志。
- 修复：`integrations/market_mcp_plugins.py` 新增 `MCPToolAuditMiddleware`（AgentScope ToolMiddlewareBase），在工具调用层记录 success/error 与参数/返回摘要，`load_market_mcp_plugins` 装配时为每个 MCP 工具追加该 middleware。市场/用户洞察、流式/非流式所有调用路径口径统一。
- 验证：假工具走 `ToolBase.__call__` + middleware，success/error 两条审计记录均正确落库（`get_tool_call_events` 断言通过）。

### 问句弱线索从硬过滤改为降权（1.3 召回优化）

- 方案：过滤分两层。新增 `_is_definite_question`（访谈员前缀 / 清洗后无受访者发言 / 整段为题干复述，三类确定性信号）继续整条丢弃；`_looks_like_question` 中仅问句线索命中（如「感觉也不怎么样」）的条目不再过滤，`_segment_score` 对其扣 0.5 降权（确定性信号仍扣 1.0），排序靠后但证据池不足时仍可入选。
- 已知教训保留：不把「也就是说/就是说」加回线索（此前实测误杀「主要就是说。」）。
- 测试：`test_toolkit` 新增 `TestQuestionFilterLayering` 6 例（前缀判提问、纯提问判提问、受访者口语不判 definite、软线索降权、软线索可入选、确定性提问永不入选），15 例全过。
- 全库统计与浏览器端到端复测：2026-11-04 执行时 146 数据库/Ollama/Reranker 整机不可达（TCP 可建连、服务无响应，疑似采集任务高负载），`verify_leak_v2.py`（已更新为 definite/soft 分层口径）与浏览器复测待 146 恢复后补跑。

