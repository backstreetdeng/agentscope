# S2 设计方案：竞品对标 Skill 包结构

状态：待用户确认｜起草：TRAE｜2026-11-02
确认后按此创建 `skills/` 包文件。本方案对齐 [docs/skill-integration-standard.md](../../../docs/skill-integration-standard.md) 第一节"完整 Skill 包"定义（SKILL.md + agents/ + references/ + assets/ + scripts/ + 依赖声明 + 产物契约）。

---

## 一、包位置与目录结构

`skills/competitor-benchmarking/`

```
skills/competitor-benchmarking/
├── SKILL.md                  # 业务目标、适用条件、四段工作流（竞品对标版）、判断规则
├── agents/
│   └── default.md            # 挂载策略：默认任务、工具优先级、L1–L3 深度路由
├── references/
│   ├── evidence-rules.md     # 字段级交叉校验规则（P0 锚定/价格阶梯/冲突三型/单元格标注）
│   ├── benchmark-matrix.md   # 对标矩阵模板 + 验收清单
│   └── so-what.md            # So What 结构、置信度标注、推断/事实分离规则
├── assets/
│   └── matrix-schema.json    # 对标矩阵 JSON Schema（前端展示与验收器共用契约）
├── scripts/
│   ├── validate_matrix.py    # 矩阵独立验收器（规则细节 S5 定义，此处定接口）
│   └── import_miit.py        # 工信部导入 + 批次对账（S4 交付，先占位声明）
└── manifest.json             # 依赖声明 + 产物契约 + 包版本哈希
```

## 二、SKILL.md 内容设计（方法论移植）

四段工作流 → 竞品对标版改造：

| 段 | 原插件规则 | 竞品对标改造 |
|---|---|---|
| ① 接收与路由 | 意图分类 / L1–L3 / 子场景路由 | 输入三型：目标车型（S1 对标）/ 发布会事件（S2 态势）/ 公告批次（S3 巡检）；深度分级决定矩阵维度数与取证预算上限 |
| ② 迭代取证循环 | 假设→检索→验证→修正；≥3 独立来源终止 | 竞品池假设 → 三源取证（`miit_*` P0 优先 → `reputation_*`/知识库 P2 → `web_search_*`/`web_reader_*` P1–P2）→ 交叉验证 → 池修正；核心维度 ≥3 源或显式缺口 |
| ③ 冲突处理 | 双边呈现 / 归因 / `[INSUFFICIENT DATA]` | 三型分治：口径（申报值 vs CLTC 宣传）、时效（公告批次 vs 当前市场）、立场（官方话术 vs 评测实测）；价格阶梯分列不合并 |
| ④ 交付路由 | research-report / comparison-analysis | 对标矩阵 + So What（references 模板）；L1 快问快答直接答复不产出矩阵 |

与插件的关键差异（改造清单）：

1. **引用体系**：`[cite:N]` → `receipt_id`（回执 ID，对齐 ResearchDAG 证据链）
2. **工具协议**：替换为项目实际工具名（`miit_search_declaration`、`reputation_*`、`web_search_local→exa→tavily`、`web_reader_local→firecrawl`）
3. **信源分级落地为工具前缀**：`miit_*`=P0、知识库/`reputation_*`=P2、`web_*`=P1/P2
4. **运行载体**：SKILL.md 只做语义驾驶；循环、状态、去重、回执由 ResearchDAG core 承担（S3）

## 三、产物契约（manifest.json 核心声明）

1. **对标矩阵**（`assets/matrix-schema.json`）：
   - 结构：`{run_id, target_model, generated_at, dimensions[], models[], cells[][]}`
   - 单元格：`{value, unit, source_tier(P0–P3), receipt_id, as_of, status(confirmed|disputed|single_source|insufficient|na), note}`
   - 硬约束：硬参数（续航/整备质量/能耗/电池能量）必须锚定 `miit.declaration`，非 confirmed 状态须附对账说明
2. **So What**：`{finding, type(opportunity|threat), confidence(high|medium|low), evidence_receipt_ids[], horizon}`
3. **运行状态**：`run-state.json` / `checkpoints.jsonl` 沿用 skill runtime 既有隔离运行机制
4. **验收门槛**（validate_matrix.py）：硬参数与 `miit.declaration` 一致率 100%；每格带 `receipt_id` 与 `as_of`；冲突格双边呈现；schema 校验通过

## 四、集成点

| 层 | 集成方式 | 落地步骤 |
|---|---|---|
| Agent | 复用 market_strategy_agent 挂载或新建专用 benchmark agent（S6 决策） | S6 |
| 引擎 | ResearchDAG core 泛化（S3）；planner 由 SKILL.md 驾驶，`eligible()` 白名单纳入 `miit_*` | S3/S4 |
| 数据 | `miit` schema（已决议）；market MCP 注册 `miit_*` 只读工具 | S4 |
| 前端 | [home.html](../../../home.html) 左侧导航新增顶级项【竞品对标】（`data-view='benchmark'`，置于【市场预测】组之后）；页面 `pages/` + `app.py` 增量 API | S6 |

## 五、12 项接入清单责任映射

| 清单项 | 由谁满足 |
|---|---|
| Registry 发现并校验完整包 | S2 包结构 + manifest |
| 读取 references / 检查 assets | S2 |
| 包内脚本隔离执行 | S2 scripts + S6 runtime |
| 数据/文件/预测/Office 能力挂载 | S4 / S6 |
| 任务图与检查点 | S3 引擎 + S6 |
| 按 run_id 恢复 | S3 / S6 |
| 代表性任务产物 | S7 |
| 独立验收发现故意错误 | S5 验收器 + S7 |
| 验收失败触发修复循环 | S6 / S7 |
| 回放与下载 | S6 |
| Codex / 网页能力对等 | 全程 |
| 场景测试覆盖（正常/缺资源/工具失败/重启/验收失败） | S7 |

## 六、确认记录（2026-11-02）

1. 包名：`competitor-benchmarking` —— **已确认**
2. Agent 挂载：**新建专用 agent**（`agents/benchmark_agent.py`，S6 实现）—— 已确认
3. 包文件已按本方案落地：`skills/competitor-benchmarking/`（SKILL.md / agents/default.md / references×3 / assets/matrix-schema.json / scripts×2 接口占位 / manifest.json）；validate_matrix.py 规则 S5 实现，import_miit.py 实现 S4 交付
4. **引擎方案变更（2026-11-02 用户决策）**：不抽取 ResearchDAG core，改为复制机制为 `utils/benchmark_research_dag.py` 独立演进，月报链路零改动。本方案第四节"ResearchDAG core 泛化（S3）"按此理解为"复制 + 适配四耦合点（问题源/白名单/预算/证据接纳）"
