# 本竞品用户洞察报告输出 · 设计方案（BCI-007）

- 任务：[BCI-007](../tasks/BCI-007/TASK.md)｜阶段：`TESTED`（HTML v1 已实现并通过验证；PPT 二期）
- 日期：2026-11-08 方案 / 2026-11-11 实现回写（Asia/Shanghai）｜执行者：TRAE
- 读者：用户（决策）、后续执行 AI
- 上位规则：[RULES.md](../RULES.md)、项目根 [AGENTS.md](../../AGENTS.md)
- 配套文档：[业务待提供清单](report-output-business-inputs.md)（开会用，不写技术）

> 本方案的约束：**不发明库里没有的指标**。凡写"有数据"，必须能在现有代码/表里指到具体字段；凡写"能做到"，必须能在 python-pptx / openpyxl 或本项目代码里指到具体能力。拿不准的写「未验证」。

---

## 0. 结论速览

### 0.1 六问直答

| # | 问题 | 结论 |
|---|---|---|
| 1 | 逐页数据契约 | 原型 11 页中，**7 页可出（其中 3 页需改口径）、4 页无数据不能出**；另加 1 页「数据边界」附录。详见 §2 |
| 2 | PPT 模板怎么落地 | 文本 token `{{RPT.P01.LEAD}}` + 表格/图表独占占位框；**.pptx 可做，.potx 直接打不开（实测）需先转 .pptx；模板缺占位符一律拒绝，不静默降级**。详见 §4 |
| 3 | 导出优先级 | **HTML 先**。理由：可页面内预览、可离线验收、无模板依赖；PPT 本机无法渲染成图（实测无 soffice/PowerPoint），质量只能靠人眼看。详见 §5 |
| 4 | 对话改稿 | **本轮明确不做**，页面不出现输入框。结构化改稿写成遗留（限定可改项 + 可回滚），解除条件见 §6 |
| 5 | 版本管理 | `bci.report` + `bci.report_version` 两份表；用 `data_fingerprint` 判定旧报告失效，**只标 stale、不自动重算、不删除**。详见 §7 |
| 6 | 共用文件与入库 | `app.py`、`home.html`、`web/bci.js` 三处按 hunk 归属本任务，不写进 `commit_paths`；独占文件逐个声明。详见 §8.4 |

### 0.2 一句话结论

> 现有能力能支撑一份**竞品侧**的用户洞察报告：画像（定量 9 项）、购车关注（16 维勾选率）、选择原因与核心对比车型、满意度（均分/推荐/口碑）、信息渠道（稀疏）、转化机会与风险（定性）。
>
> **不能支撑的是「本品（埃安RT）」那一侧**：本品定量样本 0、深访提及 3 人，原型里的 P5 左半、P9、P10 的"100% 流失"都无从计算；P2/P3 的前车来源依赖中汽数据增换购流水，库内没有；P6 首选率依赖排序题，库内也没有。

### 0.3 需要用户拍板（详见 §11）

1. 报告主体是「竞品侧」还是必须「本品 vs 竞品」——后者要等本品样本。
2. 接受 11 页 → 8 页（删 P02/P03/P06/P09，P05 改口径）吗？
3. 本轮只交付 HTML，PPT 放第二阶段，是否同意？
4. 对话改稿本轮不做，是否同意？
5. PPT 模板由谁出、何时出；是否接受「.potx 需转 .pptx、表格/图表不继承模板自定义样式」。

### 0.4 实现回写（2026-11-11）：评估结论与落地偏差

**评估结论：需改后可行。** 未改的 6 项会分别导致「契约不可验、分母错、接口无法轮询、HTML 可注入、测试不可复现」，已全部在实现中修正：

| # | 原缺陷 | 落地口径（唯一事实） |
|---|---|---|
| 1 | 块只有描述、无机器契约 | `config/report_outline.json` 为唯一契约；每块声明 `type/source/required`，`report_service.validate_outline()` 启动校验 |
| 2 | 档案聚合未按车型过滤，会把其他车型档案算进本车 | 聚合 SQL 强制 `i.vehicle_model = any(%s)`（车型集合来自 `analysis_models.json`），分母按车实时统计 |
| 3 | 定性分母写死 10/63、60/63、18/63 | 全部改为运行时读取：仅计 `template_id/template_version` 匹配、`status in ('ready','partial')`、取最大 `revision` 的档案；页面显示「x/y 份档案有值」 |
| 4 | `/generate` 返回 202 但无 job 查询接口 | 改为**同步 200**：生成前先算轻量指纹查重，命中直接复用；未命中才 build+render（5 车约 20–30s） |
| 5 | HTML 直接拼业务原文、每次生成必升版本 | 渲染器全量 `html.escape`、无脚本/外链；同指纹命中最新 `valid` 版本直接复用，不升版本 |
| 6 | 测试路径与 `home.html` 占位描述不符 | 测试在 `competitor_insight/tests/`；`home.html` 是新增 `data-bci-panel='report'` 面板并启用 tab ④ |

**实现偏差（相对原方案）**：

- 本期只交付 HTML；PPT（S5/S6）与 `report_templates.json`、`report_template_store.py`、`placeholder-spec.md` 未创建，不在本轮 `commit_paths`。
- 报告详情/预览/导出均重算轻量指纹，与版本指纹不一致时把该版本标 `stale` 并在页面横幅提示；不自动重算、不删旧版。
- 车型集合默认五款全选；标题由车型数生成（如「5 款车型竞品用户洞察报告」），代码内无车名硬编码。

---

## 1. 现有能力底座（先读，不重复造）

### 1.1 数据与接口

| 能力 | 落点 | 本方案怎么用 |
|---|---|---|
| 五车车型清单与别名 | `config/analysis_models.json`；`AnalysisService.models()` | 报告车型集合只从这里取，不在报告代码里写车名 |
| 四磁贴即时分析 | `server/analysis_service.py` → `AnalysisService.analyze(model_key)`，返回 `tiles.{profile,attention,winloss,satisfaction}` + `summary` + `sources` | 报告所有定量数字的唯一来源；报告服务逐车型调用 5 次，不复制 SQL |
| 画像分段 | 同文件 `PROFILE_SEGMENTS`（9 项：`age_band/gender/city/price_band/purchase_type/Q9_1/Q9_8/Q9_11/Q2_5`） | P01 基本特征表；**注意不含学历** |
| 16 维定义 | 同文件 `DIMENSIONS` | P04/P05/P07 的行顺序与中文名统一用它 |
| 比例口径 | 同文件 `ratio_payload()`、`sample_flag()` | 报告沿用「分子/分母 + 实际作答人数 + 样本量标记」，不另造 |
| 洞察档案（43 维） | `bci.archive` / `bci.archive_field`（DDL 见 `ops/bci_archive_ddl.sql`）；读取入口 `server/archive_api.py` 的 `ArchiveService.template/respondents/detail/quote/export` | 报告需要**跨人聚合**，现有接口只有单人明细，需新增只读聚合（§3.2） |
| 43 维字段名 | `templates/user_insight_archive_template.json` | §2 的数据契约直接引用其 `id` |
| 导出范式 | `server/export_service.py` 的 `build_xlsx` / `build_md`（全内存 bytes，二进制响应） | 报告导出沿用「内存生成 + 二进制响应」，不落临时文件 |
| 二进制上传范式 | `app.py:1677-1686`（`/api/forecast/history` 直接读 `Content-Length` 原始 body） | PPT 模板上传走同一范式，不引入 multipart 解析 |

### 1.2 真实数据现状（决定哪些页能出）

| 事实 | 数值/依据 |
|---|---|
| 五款竞品均有定量样本 | 零跑B10 41、铂智3X 39、奇瑞iCAR V23 30、海狮05 EV 31、钛3 30（`analysis-tab-feasibility.md`） |
| 每款竞品深访 3–4 人 | 同上；深访只能出原话，不能出比例 |
| 洞察档案只有 10/63 人生成 | BCI-004 试点；全量未放开 |
| 本品埃安RT | 定量 0、深访提及 3 人、0 人是埃安车主 |
| 满意度明确分数 | 13/63 |
| 8 个无来源维 | `kol_influence`、`first_choice_ranking`、`rt_awareness_channel`、`rt_attraction_ranking`、`rt_concerns`、`rt_expectations`、`reception_expectation`、`loyal_repurchase_reason` |
| 排序题 | `attention.metrics[first_ranking].status = "empty"`（库内无排序题） |
| 未购车/流失样本 | 无（`winloss.metrics[opponent_why_win].status = "empty"`） |
| 2023/2024 定量 | 未入库（BCI-001-L04） |
| 前车来源流水 | 无（原型标注「中汽数据增换购数据，范围 2026.1-8」，本项目未接入） |
| 车型级别/车身形式 | 库内无字段（BCI-006-L05） |

---

## 2. 逐页数据契约

### 2.1 总表

| 原型页 | 处置 | 状态 | 数据来源 | 无数据时怎么办 |
|---|---|---|---|---|
| P01 用户画像 | 保留，删「学历」行 | **部分** | 定量 9 项 + 档案定性 | 学历删除该行；定性只给主题+引语 |
| P02 用户来源·小鹏M03 | **不出** | **无** | 无（需中汽数据） | 不生成该页；缺口写入附录 |
| P03 用户来源·深蓝L06 | **不出** | **无** | 同上 | 同上 |
| P04 购车关注 | 保留，改口径 | **部分** | 16 维勾选率 + 分车型 TOP5 | 「品牌/产品/服务 77/23/0」不出 |
| P05 本品战胜原因 | **改页名**「竞品选择原因与核心对比」 | **部分** | `winloss.win` + `competitors` + 深访 Q29 | 本品侧整块不出 |
| P06 首选率 | **不出**（核心对比并入 P05） | **无** | 排序题缺失、`opponent_why_win` 空 | 不生成该页 |
| P07 满意度 | 保留 | **有 + 部分** | `satisfaction.overall/dimensions/recommendation/reputation` + 档案满意点 | 「进攻方向」不出 |
| P08 信息渠道 | 保留，改口径 | **部分** | 档案 `info_channels` / `content_format_preference` | KOL 行删除；不给全体百分比 |
| P09 本品吸引力 | **不出** | **无** | `rt_attraction_ranking` 无来源、本品 0 样本 | 不生成该页 |
| P10 转化机会与风险 | 保留，仅定性 | **部分** | 档案 `conversion_opportunity_risk` + 原话 | 不出现「100% 流失」这类比例 |
| P11 小结 | 保留 | **有（受限）** | 由 P01/P04/P05/P07/P08/P10 的可用指标确定性拼装 | 只总结可出部分，并列出缺口 |
| 新增 附录A 数据边界 | 新增 | **有** | 自动生成 | — |

**结论：8 个页面单元 = 7 正文页 + 1 附录；原 11 页删 4 页。**

### 2.2 字段级契约

状态说明：**有** = 现有能力可直接算；**部分** = 有字段但样本/口径受限，必须标注；**无** = 库里没有，禁止编造。

#### P01 用户画像

| 模块 | 字段 | 来源（精确到字段） | 状态 | 处置 |
|---|---|---|---|---|
| 基本特征 | 年龄段 / 性别 / 城市 / 购车价格段 / 购车类型 | `analyze().tiles.profile.metrics[key in PROFILE_SEGMENTS]` → `items[].label/count/ratio`、`answered`、`n` | 有 | 每行带 `n` 与「占比分母」 |
| 基本特征 | 婚姻 / 职业 / 家庭年收入 | 同上，`Q9_1 / Q9_8 / Q9_11`（`answers_text` JSON） | 有 | 同上 |
| 基本特征 | **学历** | 无（`PROFILE_SEGMENTS` 无学历；档案 43 维无学历） | **无** | **删除该行**，不放空行、不写"本科及以上" |
| 生活状态与价值观 | 兴趣/性格/消费观 | `archive_field(dimension_id in {personality_interest_social, consumption_values})`，`fill_mode=llm` | 部分 | 只做主题归纳 + 逐人引语；**不出现百分比**；标注"深访 N 人" |
| 购车特征 | 关注 TOP / 场景 / 动机 | `tiles.attention.metrics[attention].top`（定量）+ `archive{high_frequency_scenarios, purchase_motivation}`（定性） | 部分 | 定量出排序，定性出要点，两段分开写 |

#### P02 / P03 用户来源（前车结构）

| 模块 | 字段 | 来源 | 状态 | 处置 |
|---|---|---|---|---|
| 前车能源 / 级别 / 价格段 / 品牌 / 年龄性别 | 全部 | 无：库内无增换购流水表；`bci.archive` 无「前车」字段（`purchased_model_owned` 是**当前车**，不是前车） | **无** | **不出该页**；附录写"需中汽数据增换购流水（2026.1-8）" |

> 不使用深访「前车」替代：43 维里没有前车品牌/级别/能源字段，无法聚合。

#### P04 购车关注

| 模块 | 字段 | 来源 | 状态 | 处置 |
|---|---|---|---|---|
| 品牌是信任基础 | 产品 / 品牌 / 服务占比 | 档案 `brand_product_service_rank` 有该字段，但每车型深访仅 3–4 人，且为自由文本排序 | **无（可算比例）** | **不出 77/23/0**；最多出"深访 N 人原话摘录"，与下一模块合并呈现 |
| 产品提及率 | 16 维勾选率 | `tiles.attention.metrics[attention].items`（`count/total/ratio/answered`） | 有 | 改标注为「16 维多选勾选率，**非排序、非第一关注**」 |
| 分车型关注 TOP5 | 每车型前 5 | 同上 `.top`（5 车型各 5 项） | 有 | 表格 5 列；每列标 `n` |

#### P05 竞品选择原因与核心对比（原「本品战胜原因」）

| 模块 | 字段 | 来源 | 状态 | 处置 |
|---|---|---|---|---|
| 本品 RT vs MG07 | 两车 16 维对比 | 本品定量 0、深访 3 人 | **无** | **整块不出**，不画对比条 |
| 选择当前车辆的原因 | 16 维比例 | `tiles.winloss.metrics[key=win]`（`Q3_23__1..16`，`n=30~41`） | 有 | 逐车型表格；标题必须写"选择当前车辆的原因"，**不能写"战胜某竞品"** |
| 选择原因原话 | 逐人引语 | `tiles.winloss.metrics[key=win_quotes]`（深访 Q29） | 部分 | 每车型 3–4 条，标"深访 N 人，非比例" |
| 核心对比车型 | 自由文本归并后的提及率 | `tiles.winloss.metrics[key=competitors]`（`Q3_22_1__1`，已做别名归并） | 有 | 原 P06 的"核心对比"并入本页 |
| 竞品胜出逻辑 | 对手为什么赢 | `winloss.metrics[key=opponent_why_win].status = empty` | **无** | 不出；附录写明"无未购车样本" |

#### P06 首选率

| 模块 | 字段 | 来源 | 状态 | 处置 |
|---|---|---|---|---|
| 首选率表 | 各车型首选占比 | `attention.metrics[first_ranking].status = empty`（库内无排序题） | **无** | **不出该页** |
| 竞品胜出逻辑 | — | `opponent_why_win` 空 | **无** | 同上 |

#### P07 满意度

| 模块 | 字段 | 来源 | 状态 | 处置 |
|---|---|---|---|---|
| 整体满意度 | 均值 + 作答数 | `tiles.satisfaction.metrics[overall]`（`Q5_1`，2–10 分） | 有 | 必须同格标 `answered/n` |
| 16 维满意度 | 每维均值/低分人数 | `metrics[dimensions].items[]`（`Q5_2__1..16`） | 有 | 均分不是百分比，表头写"均分（作答 N）" |
| 推荐意愿 | 均值 + 四档 | `metrics[recommendation]`（`Q5_5`，文本折算 1–10） | 有 | 四档给人数与占比 |
| 外部口碑 | 正/负向前 5 | `metrics[reputation]` | 有 | **不并入满意度分数**，单独小表，注明不同源 |
| 满意点 / 不满意点 | 定性要点 | `archive_field(satisfaction_points / dissatisfaction_points)` | 部分 | 每车型 3–4 人，只列要点 + 引语，不出比例 |
| 进攻方向（跨车差值） | — | BCI-006-L07 v1 不做 | **无** | 不出 |

#### P08 信息渠道

| 模块 | 字段 | 来源 | 状态 | 处置 |
|---|---|---|---|---|
| 分阶段触点（认知/对比/到店） | 分阶段占比 | 档案 `info_channels` 有值但**库内无「阶段」字段** | **无（分阶段）** | 不出分阶段漏斗；改为"渠道提及人数"单表 |
| 渠道提及 | 渠道 → 人数 | `info_channels`（多值）+ `channel_normalizer` 已归并 64 种写法 | 部分 | 分母 = 该车型有值档案数（实时统计），按人去重，显式标注 |
| 内容形式偏好 | 人数/占比 | `content_format_preference`（按车型实时统计有值人数） | 部分 | 只写"n=X 中 Y 人提到"，**不出全体百分比** |
| KOL/KOC 影响 | — | `kol_influence` 无来源 | **无** | 删除该行，不写"54%" |

#### P09 本品吸引力

| 模块 | 字段 | 来源 | 状态 | 处置 |
|---|---|---|---|---|
| 产品吸引点提及率 | 四维比例 | `rt_attraction_ranking` 无来源；本品样本 0 | **无** | **不出该页** |
| 其他惊喜项 | — | 同上 | **无** | 同上 |

#### P10 转化机会与风险

| 模块 | 字段 | 来源 | 状态 | 处置 |
|---|---|---|---|---|
| 防本品流失（风险） | 风险条件 | 档案 `conversion_opportunity_risk`（llm，required） | 部分 | 归纳条件 + 原话；**禁止出现"100% 用户会流失"**这类比例 |
| 抢竞品转化（机会） | 机会条件 | 同上字段的「机会」侧 + `win_reasons` | 部分 | 同上；`rt_concerns` / `rt_expectations` 不用（无来源） |

> 前置确认：`conversion_opportunity_risk` 的题面必须确实是"什么条件下会买**本品**"。若模板问的是"当前车"，该字段不能用于本品转化，需业务确认（见 Q7）。

#### P11 小结

| 模块 | 来源 | 状态 |
|---|---|---|
| 核心结论 3–5 条 | 只使用 P01/P04/P05/P07/P08/P10 已出数字与定性要点，确定性模板句 | 有（受限） |
| 数据缺口提示 | 由 §2.1 的「无/部分」自动生成 | 有 |

> P11 不引入任何新指标；每条结论必须能回指到某个页面的字段，禁止"建议加大传播"这类无证据句。

#### 附录A 数据边界

| 内容 | 来源 |
|---|---|
| 各车型 `n/answered` 与数据源计数 | `analyze().sources`、`quant_answered_full` |
| 档案覆盖率与生成人数 | `bci.archive` 聚合 |
| 无数据页与原因 | 由契约表生成（P02/P03/P06/P09） |
| 数据截至时间 | `generated_at` + 定量/深访年度 |

---

## 3. 报告数据模型与生成链路

### 3.1 链路

```
选中车型集合 / 样本范围
   ↓
ReportService.build(model_keys)
   ├─ AnalysisService.analyze(model) × N（复用，不复制 SQL）
   ├─ ArchiveAggregator（新增只读聚合，跨人统计 43 维）
   └─ 组装 ReportContent（逐页 blocks，带 availability / source / n）
   ↓
   ├─ render_html(content) → 单文件 HTML（内联 CSS + 内联 SVG）
   └─ render_pptx(content, template) → .pptx bytes
```

### 3.2 新增的档案聚合（唯一的新查询能力）

现有 `ArchiveService` 只有单人 `detail`。报告需要"某维度在 N 人中多少人提到"。新增只读聚合，不新表：

```sql
SELECT f.dimension_id,
       count(*)                                        AS archives,
       count(*) FILTER (WHERE f.value_text <> '')       AS with_value,
       count(*) FILTER (WHERE f.fill_mode = 'none')     AS no_source,
       count(*) FILTER (WHERE f.review_status = 'suspect') AS suspect
FROM bci.archive a
JOIN bci.archive_field f USING (archive_id)
JOIN user_insight.interview i ON i.interview_id = a.interview_id
WHERE a.template_id = %s
  AND a.template_version = %s
  AND a.status IN ('ready','partial')
  AND i.vehicle_model = any(%s)          -- 车型集合来自 analysis_models.json，必须先收口
  AND a.revision = (SELECT max(revision) FROM bci.archive a2
                    WHERE a2.interview_id = a.interview_id AND a2.template_id = a.template_id)
GROUP BY f.dimension_id;
```

- 只读、只取计数，不返回业务原文；
- 引语按 `dimension_id` 另取（沿用 `ArchiveService.quote` 的归属过滤）；
- 分母不是全局常数，而是"该车型当前有效档案数"；页面显示 `x/y 份档案有值`（y 为该车型可读档案数）。

### 3.3 为什么报告不复用 `AnalysisService._summary`

`_summary()` 是"四磁贴一句话结论"，服务即时分析页；报告需要逐页、逐车型的结构化块。两者共用 `ratio_payload`/`sample_flag` 口径即可，不共用句模板。

---

## 4. PPT 模板上传怎么落地

### 4.1 库能力边界（本机实测，python-pptx 1.0.2）

| 能力 | 结论 | 依据 |
|---|---|---|
| 打开 `.pptx` | 可 | `Presentation(path)` 实测成功，读出版式与形状 |
| 打开 `.potx` | **不可** | 直接 `Presentation(.potx)` 抛 `ValueError`（content type 为 `presentationml.template.main+xml`）；把 `[Content_Types].xml` 改写成 `presentation.main+xml` 后可打开（双向均实测） |
| 文本写入 / 字号颜色字体 | 可 | `shape.text_frame` |
| 表格 | 可插入并写单元格、设填充/边距、`first_row` 等内置样式开关 | `add_table` + `table.cell()` 实测 |
| 原生图表 | 可插入柱/条/饼/环/线/散点/雷达/面积；可 `chart.replace_data()` 换同结构数据 | `XL_CHART_TYPE` 枚举实测 10 类均存在 |
| 图片占位符 | 可填充 | `PicturePlaceholder.insert_picture()` 实测成功 |
| **渲染成图片/缩略图** | **不可** | 本机 `soffice`/`libreoffice`/`powerpnt` 均不存在（`shutil.which` 全 None） |
| 继承模板自定义表格样式 | **不可按名称套用** | python-pptx 只暴露 `tblStyleId` 级别的内置开关，不能引用模板里的自定义样式 |
| 替换模板内已有图表的**结构** | 不可 | `replace_data` 只支持同类别/同系列数；改结构会破坏原图表格式 |
| SmartArt / 动画 / 批注 | 不可读写 | python-pptx 无对应 API |

### 4.2 占位符规范

**文本 token（首选）**

```
{{RPT.<页号>.<字段>}}
例：{{RPT.P01.LEAD}}   {{RPT.P04.ATTENTION_CHART}}
```

- `RPT` 固定前缀；页号 `P01..P11` 与大纲一致；字段 `[A-Z0-9_]+`。
- 大小写敏感；`{{` `}}` 内不允许空格或换行；同一 token 出现多次 = 同一字段，全部替换。
- 形状名（`shape.name = "RPT.P01.LEAD"`）作为**可选增强**，v1 不依赖；只支持文本 token，避免业务不会改形状名。

**三种特殊 token 的落位规则**

| token 类型 | 落位要求 | 程序行为 |
|---|---|---|
| 纯文本（`LEAD`/`TEXT`/`BULLETS`） | 任意文本框 | 原文本框内替换；`BULLETS` 按 token 所在段落的格式逐条生成段落 |
| 表格（`*_TABLE`） | 必须**独占一个矩形/文本框** | 记录该形状 `left/top/width/height` → 删除形状 → 同位置插入 table |
| 图表（`*_CHART`） | 必须**独占一个矩形/文本框** | 同上 → 插入原生 chart |
| 图片（`*_IMG`） | 必须是图片占位符 | `insert_picture()` |

**明确不支持**：token 写在表格单元格内且要求插入表格/图表（嵌套不允许）；一个形状内混排"文本 token + 表格 token"；SmartArt 内 token。

### 4.3 模板上传与校验

1. 上传：`POST /api/bci/report/template/upload?filename=xxx.pptx`，**原始二进制 body**（沿用 `app.py:1677-1686` 的范式，不写 multipart 解析），上限 20 MB。
2. 转换：`.pptx` 直接用；`.potx` 先改写 `[Content_Types].xml` 为 `presentation.main+xml` 并存为 `.pptx`（实测可行）；`.ppt`/`.key` 直接 415。
3. 解析校验，返回：
   - `hit`: 命中的 token 列表（页/字段/形状名/类型）
   - `missing`: 缺失的**必需** token
   - `unknown`: 模板里存在但大纲没有的 token
   - `misplaced`: 表格/图表 token 位置不合法
   - `coverage`: `已覆盖模块数 / 总模块数`
4. **判定规则**：
   - `missing` 含任一必需 token → `422 template_no_placeholder`，**拒绝导出 PPT**，返回缺失清单与"请补齐占位符"；**不静默改用标准模板**。
   - 仅缺可选 token → 允许，但导出结果必须带"该模块未进入 PPT（模板缺少占位符）"的显式说明，且页面同时提供 HTML 完整版。
   - `unknown` 一律拒绝（避免业务以为填了其实没填）。
5. 落盘：`data/competitor-insight/report-templates/<sha256>.pptx` + 登记 `config/report_templates.json`（`template_id/name/version/placeholder_hash/created_at`）。不覆盖同名文件；同 sha256 视为同一模板。
6. 标准模板：不提交二进制。`GET /api/bci/report/template/standard` 由代码实时生成 8 页骨架（含全部 token），供业务照抄版式。

### 4.4 业务要做什么（交给业务的话）

- 交一个 `.pptx`，页数 ≥ 8，每页有标题框与内容框；
- 表格/图表区域画一个**空白矩形**并在里面写对应 token；
- 不要用 SmartArt、艺术字、动画承载数据；
- 由我方跑一次"校验"并返回缺失清单，业务补齐后再交版。

---

## 5. 导出优先级：HTML 先

### 5.1 理由

1. **可验收**：HTML 能在页面内直接渲染、可在浏览器逐页验收；PPT 本机**无法渲染成图**（§4.1 实测），只能靠人打开 PowerPoint 看，CI 与 Playwright 都覆盖不到版式。
2. **无外部依赖**：HTML 不依赖模板、不依赖字体文件、不依赖 Office；PPT 依赖业务模板（未提供）。
3. **已有范式**：`export_service.build_xlsx/build_md` 已是"内存 bytes + 二进制响应"，HTML 照此实现即可。
4. **风险前置**：先把数据契约跑通，PPT 只是换渲染器；顺序反了会在版式上反复返工。

### 5.2 最小可交付（v1.0）

- 输入：车型集合（默认五车全选）+ 样本范围（默认定量全量 / 深访全部已生成档案）。
- 输出：**单文件 HTML**，8 个页面单元，内联 CSS + 内联 SVG（不引外部 CDN），每页带 `n` / `answered` / 数据来源脚注。
- 页面能力：生成、列表、详情、下载 HTML。
- 明确不做：PPT、改稿、多年对比、本品侧。

### 5.3 第二阶段（v1.1 PPT）

- 先出**代码生成的标准 8 页 PPT**（不依赖业务模板），验证 table/chart 位置与字号；
- 再做业务模板上传与 token 填充（§4）。

---

## 6. 对话改稿

### 6.1 本轮结论：不做

- 原型里的"小结收敛 3 条 / 加一页 / 标题精炼"是 3 条正则，看起来能用、实际是兜底，**不能保留这种入口**。
- 本轮页面**不出现任何输入框、不出现"重新写"按钮**；只有"重新生成"（整份重算，产生新版本）。

### 6.2 后续结构化改稿的最小形态（供立项讨论）

| 项 | 设计 |
|---|---|
| 可改范围 | 仅 `lead` 一句话、`bullets` 文本、页面标题；**数字、表格、图表不可改** |
| 存储 | 新增 `bci.report_section_override(report_version_id, section_key, original_text, override_text, edited_by, edited_at)` |
| 生成方式 | 改稿生成**新版本**（`version_no + 1`），不原地修改；原版本永久保留 |
| 校验 | 覆盖文本中的数字若与原值不一致 → 拒绝保存（数字白名单比对） |
| 回滚 | 一键"回到原版"= 清空该版本 override 并重新渲染 |
| 不做什么 | 不做自然语言指令解析、不做跨页联动改写 |

### 6.3 解除条件

- 用户确认立项（新任务编号需确认）；
- 至少 20 份历史报告作为回归样本；
- 数字白名单校验规则先落地（否则改稿会改数字）。

---

## 7. 版本管理

### 7.1 存储

```sql
-- 新表，不改现有 bci.archive*
bci.report (
  report_id uuid PK, title text, model_keys jsonb, sample_scope jsonb,
  template_id text NULL, created_by text, created_at timestamptz
)
bci.report_version (
  report_version_id uuid PK, report_id uuid FK, version_no int,
  content jsonb, html text, data_fingerprint char(64),
  source_snapshot jsonb, status text CHECK (status IN ('valid','stale')),
  stale_reason text, generated_at timestamptz,
  UNIQUE (report_id, version_no)
)
```

- `content` 是逐页 blocks 的结构化 JSON（可回指字段与 n），`html` 是渲染产物（避免每次重算）。
- 不存业务原文快照；引语按 `source_ref` 现取，取不到时标 `source_missing`（沿用 BCI-004 口径）。

### 7.2 数据版本指纹

`data_fingerprint = sha256(json.dumps(snapshot, sort_keys=True))`，snapshot 固定包含：

| 组成 | 取值 |
|---|---|
| 大纲版本 | `config/report_outline.json.version` |
| 分析配置 | `config/analysis_models.json.version/updated` |
| 逐车型样本 | `key` + `sources{quant,interview,reputation,miit}` + `quant_answered_full.n` |
| 逐档案版本 | 每个用到的 `interview_id` 的 `(template_id, template_version, revision, updated_at)` |
| 模板 | 业务模板 `sha256`（标准模板记 `standard@1`） |
| 渲染器版本 | `report_render_html.VERSION` / `report_render_pptx.VERSION` |

### 7.3 失效规则

- 打开详情/导出时重算指纹：不一致 → 该版本 `status='stale'`，返回 `stale:true` + `stale_reason`（哪个车型样本数变了 / 哪些档案 revision 变了 / 模板换了）。
- **不自动重算、不删除旧版本**；页面给"数据已更新，重新生成"入口。
- 归档/分析口径变化（如全量 63 人跑完、模板升级）同样触发 stale；旧报告仍可下载，但顶部必须有失效横幅。

---

## 8. 接口、前端与共用文件

### 8.1 接口（`/api/bci/report/*`）

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/outline` | 8 页大纲 + 每模块 availability（另返回 `sources` 来源登记表） |
| GET | `/options` | 车型清单、各车型样本数、档案模板与版本 |
| POST | `/generate` | `{model_keys[]}` → 同步 **200**（`created/reused/report_version_id`）；生成前按指纹查重，命中直接复用 |
| GET | `/versions` | 版本列表（含 `valid/stale`） |
| GET | `/detail?id=` | 结构化 content + stale 判定 |
| GET | `/preview?id=` | 单文件 HTML，`inline` 预览 |
| GET | `/export?id=` | 单文件 HTML 下载（`attachment` + UTF-8 文件名） |

> PPT 相关接口（`/template/*`、`format=pptx`）随 S5/S6 二期落地，本期未注册，前端不出现对应入口。

错误码沿用 BCI 既有约定：`400` 参数、`404` 不存在、`409` 冲突、`413` 过大、`415` 格式不支持、`422` 模板不可用、`503` 数据库不可用。

### 8.2 前端

- `web/bci-report.js`：自包含（不 import `bci.js`），`window.BciReport.init(host)`，沿用档案模块"面板展开才加载"的策略。
- `web/bci-report.css`：仅本模块样式。
- 页面结构（tab ④）：上方「报告配置（车型复选 + 范围汇总）」，下方左「版本列表」、右「逐页预览」；主按钮为「生成报告 / 下载 HTML」。PPT 入口本期不渲染。
- 不得出现假入口：改稿输入框、未实现的按钮一律不渲染；不可用按钮用 `disabled` + 明确原因。

### 8.3 新增文件（独占，2026-11-11 实际落地）

```
competitor_insight/config/report_outline.json
competitor_insight/server/report_archive_aggregate.py
competitor_insight/server/report_service.py
competitor_insight/server/report_render_html.py
competitor_insight/server/report_api.py
competitor_insight/web/bci-report.js
competitor_insight/web/bci-report.css
competitor_insight/tests/test_report_service.py
competitor_insight/tests/test_report_render_html.py
ops/bci_report_ddl.sql
ops/apply_bci_report_ddl.py
```

二期（S5/S6，未创建）：`report_render_pptx.py`、`report_template_store.py`、`report_templates.json`、`templates/report/placeholder-spec.md`、`tests/test_report_render_pptx.py`、`tests/test_report_template_store.py`。

### 8.4 共用文件与 hunk 归属

| 文件 | 本任务改动 | 入库处理 |
|---|---|---|
| `app.py` | GET 分发加 `/api/bci/report/` 前缀；POST 分发加同前缀；新增 `_handle_bci_report_get/post` 两个方法与惰性单例 | **不写进 `commit_paths`**；只把本任务 hunk 写入索引，其他任务改动留在工作区 |
| `home.html` | 启用 tab ④（去掉 `disabled` 与「下一步」角标）、替换 `data-bci-panel='report'` 的"本轮未开发"占位、新增 `bci-report.css/js` 两个引用 | 同上 |
| `competitor_insight/web/bci.js` | tab 切换回调加 `if (key === 'report') initReport(root);` + `initReport()` | 同上（用户明确要求按 hunk 处理） |
| `competitor_insight/tasks/tasks.md`、`BOARD.md`、`HANDOFF.md` | 新增/同步任务行 | 共享状态文件，由当前执行者维护；**不整目录声明** |

`commit_paths`（本任务独占，文件级检查）：

```
competitor_insight/config/report_outline.json
competitor_insight/server/report_archive_aggregate.py
competitor_insight/server/report_service.py
competitor_insight/server/report_render_html.py
competitor_insight/server/report_api.py
competitor_insight/web/bci-report.js
competitor_insight/web/bci-report.css
competitor_insight/tests/test_report_service.py
competitor_insight/tests/test_report_render_html.py
ops/bci_report_ddl.sql
ops/apply_bci_report_ddl.py
competitor_insight/docs/report-output-design.md
competitor_insight/docs/report-output-business-inputs.md
competitor_insight/tasks/BCI-007
outputs/competitor-insights/BCI-007
```

> 注意：`server/`、`web/`、`config/`、`docs/`、`tests/` 都是共享目录，**逐文件声明**，不写整目录。

---

## 9. 实施顺序、依赖与验收

| # | 步骤 | 产出 | 验收 | 依赖 | 状态 |
|---|---|---|---|---|---|
| S1 | 大纲与契约固化 | `config/report_outline.json` + `report_service.py` 纯函数 + 5 车型真实快照 | 8 个页面单元全部生成；每个数字可回指 `analyze()`/档案聚合；无硬编码车名与数字 | 无 | 完成 |
| S2 | HTML 渲染与下载 | `report_render_html.py` + 导出接口 | 单文件 HTML 可离线打开；无外部 CDN；8 页齐全；脚注含 n/answered | S1 | 完成 |
| S3 | 版本与失效 | DDL + `report_version` + 指纹判定 | 改动档案 revision 后旧版本变 stale；旧版仍可下载 | S1 | 完成 |
| S4 | 页面接入 | `report_api.py` + `bci-report.js/css` + 三处共用文件 hunk | 7860 tab ④ 可用；无 JS 报错；不可用项有原因 | S2/S3 | 完成（7861 实测） |
| S5 | 标准 PPT | `report_render_pptx.py` + `/template/standard` | 8 页 PPT 可打开；表/图位置正确；无占位符残留 | S1 | 二期 |
| S6 | 业务模板上传 | `report_template_store.py` + 上传/校验接口 | 缺 token 返回 422 且清单准确；`.potx` 可转；无静默降级 | S5 + **业务模板** | 二期（阻塞：业务未提供模板） |
| S7 | 浏览器 E2E | Playwright 脚本 + 截图 | 生成→预览→下载→变 stale→重新生成 全链路 PASS | S4 | 完成（生成/复用/预览/下载/无 console 报错） |
| S8 | 入库 | Git 提交 | `check_board.py` PASS；只含本任务 hunk | 用户授权 | 本次提交 |

**必须等外部条件**：S6 ← 业务提供 `.pptx`；P02/P03 ← 中汽数据增换购流水；本品侧（P05 左半/P09）← 本品定量样本 ≥30；多年对比 ← 2023/2024 定量入库；满意度完整 ← 13/63 提升。

---

## 10. 风险与已知边界

1. **报告标题不能叫"本竞品"却没本品**：v1 建议命名「XX 组竞品用户洞察报告」，页脚写明"本期不含本品侧"。这是业务口径问题，见 Q1。
2. **深访只覆盖 10/63 人**：报告定性块的分母是"已生成档案人数"，不是 63；页面必须显示，否则会被当成全量。
3. **`Q3_23` 语义**：是"选择当前车辆的原因"，不是"战胜某竞品的原因"；P05 标题与脚注必须改。
4. **满意度均分 ≠ 满意度比例**：16 维是 2–10 分均分，不能画成百分比条形图。
5. **外部口碑与问卷不同源**：不合并成单一分数（沿用 BCI-006 口径）。
6. **HTML 单文件体积**：8 页内联 SVG 预计 100–300 KB，可接受；不引外部字体。
7. **PPT 版式风险**：模板自定义表格样式/图表配色不会被继承；如业务强要求 VI 完全一致，需人工在 PowerPoint 里调版（记为人工步骤）。
8. **未验证项**：`.potx → .pptx` 转换后的模板在 PowerPoint 里打开是否保留母版（本机无 Office，未验证）；`fit_text` 实际缩放效果未验证。

---

## 11. 待用户拍板

| # | 问题 | 影响 | 建议默认值 |
|---|---|---|---|
| Q1 | 报告主体是竞品侧，还是必须「本品 vs 竞品」？ | 决定 P05/P09/P10 是否存在 | 本期只做竞品侧，本品侧列为待补样本 |
| Q2 | 接受 11 页 → 8 页（删 P02/P03/P06/P09，P05 改口径）？ | 决定整份结构 | 接受 |
| Q3 | 本轮只交付 HTML、PPT 二期，是否同意？ | 决定交付节奏 | 同意 |
| Q4 | 对话改稿本轮不做，是否同意？ | 避免假入口 | 同意，写遗留 |
| Q5 | PPT 模板谁出、何时给？ | S6 阻塞 | 业务出模板，我方给占位符清单与标准样例 |
| Q6 | 报告读者与用途（内部策略会/对外/经销商）？ | 决定详略与口径 | 内部策略会 |
| Q7 | `conversion_opportunity_risk` 题面问的是"本品"还是"当前车"？ | 决定 P10 能否用于本品转化 | 需业务确认 |
| Q8 | 报告样本范围：定量全量 + 深访全部已生成档案？ | 决定分母 | 是 |
| Q9 | 是否有品牌 VI（logo/主色/字体字号）规范文件？ | 决定 HTML/PPT 视觉 | 无则用中性样式 |
| Q10 | 是否需要中英双语？ | 影响模板与文案 | 本期中文 |

---

## 附录 A 探针结果（2026-11-08，python-pptx 1.0.2）

| 检查 | 结果 |
|---|---|
| 图表类型 COLUMN/BAR/STACKED/PIE/DOUGHNUT/LINE/XY_SCATTER/RADAR/AREA | 全部可用 |
| 默认模板版式与占位符 | 可枚举 `slide_layouts` 与 `placeholder_format.type` |
| 表格写入 | 成功；`first_row/first_col/last_row/last_col/horz_banding` 可设 |
| 原生图表写入 + 复开 + `replace_data` | 成功 |
| 图片占位符 `insert_picture` | 成功 |
| `.potx` 直读 | 失败（content type `template.main+xml`） |
| `.potx` 改写 `[Content_Types].xml` 后 | 可打开；反向改写同样可打开 |
| `TextFrame.fit_text` | API 存在；实际缩放效果依赖字体，未验证 |
| 本机 PPT 渲染 | 无 `soffice`/`libreoffice`/`powerpnt` |
| openpyxl 原生图表 | 可用（备用导出格式） |

探针脚本：`temp/20261108-bci007-probe/probe_pptx.py`、`probe_pptx2.py`；运行日志见 `outputs/competitor-insights/BCI-007/20261108-pptx-probe/probe.log`。

## 附录 B 占位符清单（给业务照抄）

| 页 | 字段 token | 类型 |
|---|---|---|
| P01 | `{{RPT.P01.TITLE}}` / `{{RPT.P01.LEAD}}` / `{{RPT.P01.BASIC_TABLE}}` / `{{RPT.P01.LIFESTYLE}}` / `{{RPT.P01.PURCHASE}}` | 文本/表格/文本/文本 |
| P04 | `{{RPT.P04.TITLE}}` / `{{RPT.P04.LEAD}}` / `{{RPT.P04.ATTENTION_CHART}}` / `{{RPT.P04.TOP5_TABLE}}` | 文本/文本/图表/表格 |
| P05 | `{{RPT.P05.TITLE}}` / `{{RPT.P05.LEAD}}` / `{{RPT.P05.WIN_TABLE}}` / `{{RPT.P05.COMPETITOR_TABLE}}` / `{{RPT.P05.WIN_QUOTES}}` | 文本×2/表格×2/文本 |
| P07 | `{{RPT.P07.TITLE}}` / `{{RPT.P07.LEAD}}` / `{{RPT.P07.OVERALL}}` / `{{RPT.P07.SAT_TABLE}}` / `{{RPT.P07.REPUTATION_TABLE}}` / `{{RPT.P07.POINTS}}` | 文本×2/文本/表格×2/文本 |
| P08 | `{{RPT.P08.TITLE}}` / `{{RPT.P08.LEAD}}` / `{{RPT.P08.CHANNEL_TABLE}}` / `{{RPT.P08.CONTENT}}` | 文本×2/表格/文本 |
| P10 | `{{RPT.P10.TITLE}}` / `{{RPT.P10.LEAD}}` / `{{RPT.P10.RISK}}` / `{{RPT.P10.OPPORTUNITY}}` | 文本×4 |
| P11 | `{{RPT.P11.TITLE}}` / `{{RPT.P11.BULLETS}}` | 文本×2 |
| 附录A | `{{RPT.APPENDIX.TITLE}}` / `{{RPT.APPENDIX.BOUNDARY}}` | 文本×2 |

> 表格/图表 token 必须各自独占一个空白矩形；文本 token 可放在同一文本框的多段中。
