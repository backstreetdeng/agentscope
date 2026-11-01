# TRAE第一项任务（T0）：复核已有审计，输出实施准备报告（只读）

> **直接复制到TRAE IDE执行。**当前项目已有一套2026-10-30的代码审计、接口契约与访谈Schema；不要重复从零架构设计。**本轮不修改任何业务代码、数据库或页面。**本轮增加对同事CATARC工程案例与工程使用规范的只读借鉴评审，禁止照搬或安装。****

## 一、责任与边界

你（TRAE）负责**乘用车用户洞察智能体**。Codex继续负责**市场战略智能体**，现有市场预测保持不变。所有Agent使用现有网页工程及共享基础；共享文件改动必须先评估冲突，不允许擅自覆盖其他开发工具的修改。

用户洞察的首期结果是“**战胜战败及购车决策链证据问答**”：用户在原网页提问，后端从已准备的访谈问答/标签/证据中检索，AgentScope只依据可核验证据归纳，页面显示匿名受访者编号、题号、原话及真实时间精度。

第一阶段不需要重新批量转写全部音频、不需要重新训练模型、不接入新的重型Agent/Workflow框架。

## 二、首先读取以下基线资料（注意版本与来源）

1. `用户洞察智能体_代码审计与MVP开发方案_20261030.md`：既有实际工程审计、程序入口、检索设计、修改清单与测试。
2. `用户洞察智能体_接口契约_20261030.md`：同步API、后续SSE设计、引用规则。
3. `用户洞察智能体_访谈Schema_20261030.sql`：`user_insight`七张数据表的DDL（**只阅读，不执行**）。
4. 原数据底座`README.md`及`00_manifest/manifest.json`、`coverage_matrix.csv`、`data_quality_report.md`、`SHA256SUMS.txt`（如在授权工作区可找到）。
5. 项目当前真实源码、环境配置、前端资源与Git状态；必要时查阅汇报HTML，但它不能代替工程运行证据。

**信息安全：**用户访谈原文、PII、内部秘钥和数据库凭据不得向云端TRAE模型/插件、外部API或远端Git提交。若当前TRA E执行模式不满足本地敏感数据访问授权，则只阅读经脱敏的文档、Schema和代码结构，不打开原始访谈与逐行问卷；输出缺口，不尝试绕过控制。

## 三、优先复核已知审计结论，不要重复发明

请逐项通过**本地源码/依赖/接口**核对是否仍然成立，并输出“确认/变化/暂不可证实 + 证据文件和行号/函数名”：

1. 项目根目录及Python环境是否与审计报告一致；AgentScope是否依旧是**2.0.3**；实际构造是否是`Agent + ReActConfig + Toolkit`。
2. Web是否还是`ThreadingHTTPServer`，而**非FastAPI**；入口API是否还是`/api/chat`与`/api/assistant/chat`。
3. 当前网页是否依旧是**同步JSON，没有SSE**；进度是否为`startDemoProgress()/startExecutionNarrative()`前端模拟。
4. `AGENT_RUN_LOCK`是否仍将聊天请求串行化，`AgentEventLoopRunner`是否仍负责异步Agent调用。
5. 是否已有`SkillRunContext`、run-state.json/checkpoint、Job Manager；这些机制能否用于用户洞察，避免重建Runtime。
6. `user_insight_tagger`是否仅是词典规则工具，无法返回数据库中的真实受访者证据；当前用户洞察Agent是否仍未接入访谈向量检索。
7. 旧rag-engine是否仍属独立项目，WeKnora是否仍未接入当前Agent；Embedding1024维、Reranker接口若无法安全探活，只报告配置和历史审计值。
8. 确认`legacy_workbench.html`现有`reportArea`、`app.py`、`agents/user_insight_agent.py`、`tools/custom_tools.py`等文件当前结构及Git改动归属。

**不得把历史报告中的FastAPI、SSE或实际状态未经验证地写成已存在。**若2026-10-30审计与当前代码不符，优先记录差异，不直接修复。

## 四、复核已有数据和SQL/API契约

仅对有授权、能访问的数据包执行只读元数据统计；缺失文件记为“待提供/待核实”。

### A. 数据基线与数量差异

- README：63位受访者、85题、`qa_pairs.csv` 5,355条、`answer_evidence.jsonl` 81,437条、`tags.csv` 5,355条、`tag_evidence.csv` 45,244条。
- 代码审计：JSON原始证据77,380条、去重77,159条；标签证据明细25,073条；另2位DOCX回退。
- 这些**数字不一致，不能直接混成同一口径**。以manifest/实际文件、去重逻辑、源文件版本说明为准，输出核对表；若无法访问源文件，就保持未核实状态。
- 61位结构化JSON对应秒级证据，2位DOCX回退对应段落级证据；重点检查`time_precision`，不为段落证据生成秒数。
- 29条标签证据未自动关联的描述需与实际数据版本核对；不得根据别名猜测tag_id。

### B. Schema只读审核

审查既有`user_insight`七张表及索引：

- 证据`answer_id`/`interview_id`/`question_id`是否有跨表一致性检查；
- `time_precision=second`与`start_sec/end_sec`是否存在“标秒级却无秒值”风险；
- `tag_evidence`和`evidence`是否是两个独立来源；
- 数据库主键`evidence_id`与一次响应中的`[E1]`编号是否建立明确映射；
- `retrieval_run.question`是否涉及敏感信息存储与保留期限；
- 数据库的原有`public.documents/chunks`是否能保持原样。

仅输出**最小修订建议**，禁止在T0运行`CREATE TABLE/ALTER TABLE/CREATE EXTENSION`。

### C. API契约审核

首期优先采用现有契约：

`POST /api/insight/interview/query`

请求：`question`、白名单`filters`、`top_k`、可选`session_id`；响应：`run_id`、`status`、`answer`、`evidence[]`、`retrieval`、`warnings[]`。

- `evidence[]`必须由后端数据库证据生成，不从LLM文本抽取；
- `[E1]`等展示引用必须能映射回某个稳定数据库证据ID；
- 无证据返回明确受限回答，不虚构受访者原话；
- 依赖故障返回明确错误，不以LLM常识替代；
- `POST /api/insight/interview/stream`、`GET /api/insight/runs/{run_id}`为后续扩展，**不是第一阶段完成条件**；
- 识别契约与实现方案中`top_k`默认值、上限、HTTP错误码等不一致处，提出一个需统一的建议，但不要当场修改原文件。

## 五、拟定最小可执行开发路线（先只设计）

请以确定性Python阶段链为第一版Workflow：

`API入参/权限 → 白名单过滤 → PostgreSQL召回 → Embedding/Reranker → 证据打包 → AgentScope受约束归纳 → 引用校验 → 同步JSON → 证据卡片`。

请提出以下开发步骤及每一步验收门槛：

- T1：开发期Harness（现有规则、Git协作/工作树、pytest/PowerShell校验入口）；
- T2：数据冻结、专用Schema与导入计划（先执行前备份/事务/回滚评估）；
- T3：InterviewRetrievalService与新Tool，真实证据可回源；
- T4：独立同步查询API，原网页`reportArea`增加证据卡片；
- T5：战胜战败专题研究Skill；
- T6：定量变量与SQL/Python统计Skill；
- T7：群体对比、配置建议与联合洞察；
- T8：SSE、任务Checkpoint和运行期Harness增强。

开发原则：保留AgentScope 2.0.3、`ThreadingHTTPServer`和原有路由；对`app.py`等共享文件只能设计向后兼容的最小补丁；首期不修改市场战略、预测、首页、`public`旧RAG表，不重构全站。

## 五-A、评估同事优秀案例与工程规范（只读）

已知参考是私有CATARC项目 `2388976762yu-hash/CATARC`，以及之前整理的《CATARC 工程实践借鉴与现有网页智能体架构优化指导书 V1.1》。

**前置要求**：仅在有权访问的本地副本或明确授权的仓库连接下阅读；不可把私有业务数据、密钥或CATARC原项目源码复制到用户洞察工程。无权限则依据本指南摘要输出“待核实”，不要中断本轮其他审计。

如有授权，优先查看以下文件（以当前实际路径为准）：

- 根 `AGENTS.md` / 项目 `AGENTS.md`：项目识别、真源优先级、跨项目禁止写入及验收闸口。
- `projects/industry-tracking-v2/WORKFLOW.md`：任务启动、停止、续跑和验收说明。
- `projects/industry-tracking-v2/docs/HARNESS.md`：阶段图、Hard Gate、Provenance、Checkpoint、预算与恢复。
- `projects/industry-tracking-v2/config/tracking_v2_protocol.json`：机器可读阶段/状态契约。
- `projects/industry-tracking-v2/scripts/verify_harness.py`：隔离临时数据库验证，不写正式工作数据。
- `CATARC_Codex_Architecture_Guide_v1.1.md`（若已提供）：工程借鉴原则及职责划分。

请输出**“CATARC机制 → 当前用户洞察可复用的思想 → 在现有AgentScope/HTTP服务中的具体接入点 → 应当舍弃的复杂度”**对照表，且区分：现有已实现 / 有类似能力 / 尚未实现。

建议首期仅选择SSOT、阶段输入输出契约、Hard Gate、引用/来源留痕、测试隔离、Git协作约束。长任务Job/取消/恢复与成本审计在真实需要时增量建设。

重点核实：现有`SkillRunContext`是否已有可复用的状态/Checkpoint；不要因看到CATARC的`jobs.py`就重新写一套Job Manager。

## 六、你本轮必须输出的结构

请在聊天中按此顺序提交：

1. **审计结论复核表**：过去结论、当前代码证据、是否仍有效、风险。
2. **数据资源与数量差异表**：实际可访问文件、计数口径、版本、未核实项。
3. **Schema与API契约风险表**：只指出需改/可直接用/待确认，附出处。
4. **现有调用链图**（真实状态，不得写成FastAPI+SSE）和**MVP目标调用链图**。
5. **Workflow/Runtime/Harness复用矩阵**：哪些现成机制复用、哪些确实需要新增。
6. **CATARC优秀案例借鉴矩阵**：至少比较SSOT、阶段契约、Hard Gate、Provenance、Verify、Checkpoint、开发协作，并列出不应照搬的实现。
7. **未来文件影响表**：新增/修改文件、涉及的Codex共享区域、兼容性和回滚方法。
8. **T1—T8阶段开发顺序**：每步前置条件、交付、测试命令、数据安全要求、完成门槛。
9. **第一条真实证据问答闭环验收样例**：只使用脱敏样例描述，不出现真实个人访谈原文。
10. **阻断问题清单**：只列不能凭现有源码/资料解决的事项，并建议默认处理路径。

## 七、执行限制和停止条件

- **本轮只读**：不改代码、`.env`、数据库、网页、Git分支、不安装依赖、不执行带副作用脚本。
- 可以读取版本、代码、文档、Git状态；未经授权不能连接生产数据库或输出内网密钥。
- 如果数据包缺失，不凭空创建假数据/假测试通过记录。
- 若存在其他工具未提交的修改，记录并停止任何可能覆盖的操作。
- 完成报告即停止，等待我审查后再实施T1；无需再次重复通用架构解释。

现在请先执行T0复核并输出报告。
