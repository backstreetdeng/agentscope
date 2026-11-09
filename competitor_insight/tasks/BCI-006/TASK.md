# BCI-006：竞品洞察 · 即时分析 tab

```
task_id: BCI-006
title: 竞品洞察 · 即时分析 tab
stage: TESTED
owner: TRAE
port: 7860
frozen_paths: none
commit_paths: competitor_insight/server/analysis_service.py, competitor_insight/config/analysis_models.json, competitor_insight/web/bci-analysis.js, competitor_insight/web/bci-analysis.css, competitor_insight/tests/test_analysis_service.py, competitor_insight/tests/e2e_analysis_api.py, competitor_insight/tests/e2e_analysis_page.py, competitor_insight/docs/analysis-tab-feasibility.md, competitor_insight/tasks/BCI-006/, outputs/competitor-insights/BCI-006/20261107-analysis/, outputs/competitor-insights/BCI-006/20261107-feasibility/, home.html, competitor_insight/web/bci.js
updated: 2026-11-09
blocked: no
next: 用户明早验收 7860「即时分析」tab；业务确认 §8 数据缺失清单的后续补数范围
evidence: outputs/competitor-insights/BCI-006/20261107-analysis/
```

## 1. 目标与边界

- 目标：竞品洞察第 3 个 tab「即时分析」，按**真实库数据**产出四类磁贴（用户画像 / 购车关注 / 战胜战败 / 满意度）+ 一条确定性综合结论；每个指标给分子、分母与空态原因。
- 边界：
  - 只读 `user_insight.*`（定量/定性）、`public.new_car_reputation_*`（口碑）、`miit.ods_pz_*`（配置）。
  - 复用 `customer_insight/quant_service.py`、`insight_service.py`、`segment_aliases.py`，不复制平行实现。
  - 前端自包含放 `competitor_insight/web/`，样式沿用现有深蓝 token，不污染全局。
  - 共享文件只做竞品洞察相关追加：`app.py` 路由、`home.html` tab 容器与资源引用。
- 禁止项：
  - 不改 `app.py` 深度调研部分、`home.css` 的 `.insight-ctx[hidden]`、智能问答链路。
  - 不改其他任务的文件内容；不整目录声明 `web/`、`templates/`、`config/`。
  - 不编造数据：算不出的指标显示空态并写明原因，不用中性占位或模型兜底。
  - 不使用原型五车（埃安RT/小鹏M03/深蓝L06/银河TT/MG07）作为默认范围。

## 2. 验收标准（必须可判定）

| # | 验收项 | 判定方式 | 证据要求 |
|---|---|---|---|
| A1 | 车型下拉只出现库内真实车型，且每款显示四源计数 | 对比 `GET /api/bci/analysis/models` 与 SQL 计数，抽查 ≥5 款 | 接口 JSON + SQL 结果 |
| A2 | 四个磁贴数据全部来自可复算查询 | 每个指标能从响应字段回溯到题号/表名，随机抽 5 项重算 | 重算脚本输出 |
| A3 | 不可做指标显示空态 + 原因，不显示 0 | 页面上检查关注第一排序、Q5_5、竞品胜出逻辑 | 浏览器截图 + DOM 断言 |
| A4 | 所有比例同时给分子/分母与样本量标记 | DOM 断言比例卡片含 `n=` 与分子分母 | 端到端断言脚本 |
| A5 | 新服务单测覆盖 | `python -m pytest competitor_insight/tests -q` 通过，新增用例 ≥8 | 测试日志 |
| A6 | 浏览器端到端 | 真实服务 + 真实库，脚本可重跑，断言四磁贴均有真实数字 | 截图 + 断言日志 |
| A7 | 不改无关链路 | `git diff` 中 `app.py`/`home.html` 仅竞品洞察 hunk；智能问答与深度调研零改动 | diff 证据 |

## 3. 步骤与结果

| # | 步骤 | 状态 | 实际结果 | 证据 |
|---|---|---|---|---|
| S1 | 只读探查四源可得性与逐指标口径 | 完成 | 7 轮探查脚本；四源与题目覆盖见测评文档 §1–§7 | `temp/20261107-bci006/probe_*.py` |
| S2 | 输出可行性测评与车型范围结论 | 完成 | [analysis-tab-feasibility.md](../../docs/analysis-tab-feasibility.md) | 本目录 `manifest.json` |
| S3 | 实现 `analysis_service` 四磁贴取数与口径 | 完成 | 四磁贴 + 确定性结论；车型走 `config/analysis_models.json`；Q29↔Q3_23、Q27/Q28↔Q3_24_1、Q1 单列画像 | `competitor_insight/server/analysis_service.py` |
| S4 | 实现 `/api/bci/analysis/*` 接口并注册路由 | 完成 | `GET /api/bci/analysis/models`、`GET /api/bci/analysis/analyze?model=`；真实服务 200 | `app.py` BCI 追加段 |
| S5 | 实现 `bci-analysis.js` / `bci-analysis.css` 并接入 tab | 完成 | 车型下拉、四源徽标、综合结论、四磁贴、空态与明细表；tab ③ 已启用 | `competitor_insight/web/bci-analysis.*`、`home.html`、`bci.js` |
| S6 | 单测 + 端到端断言脚本 | 完成 | 18 条单测通过；API 断言全通过；浏览器断言全通过 | `tests/test_analysis_service.py`、`tests/e2e_analysis_api.py`、`tests/e2e_analysis_page.py` |
| S7 | 浏览器验收与入库 | 完成 | 浏览器 E2E 全通过（B10 n=41、钛3 n=30）；截图、断言、五车数字汇总已归档；提交本任务文件 | `outputs/.../20261107-analysis/`、`metrics_summary.json` |
| S8 | 四子功能改为入口卡片展开/收起 | 完成 | 默认只展开「用户画像」，四卡横排、`已选 x/4` 与「已展开/点击展开」标记；展开块按选中顺序纵向堆叠，收起即不占版面；只改显示策略，未加指标/图表 | `bci-analysis.js`、`bci-analysis.css`、`e2e_analysis_page.py` |
| S9 | 「换车型重新查询失败」定位与常驻 | 完成 | 根因为 7860 服务被父 shell 回收，浏览器连接层失败（`Failed to fetch`），非接口逻辑；WMI 脱离终端启动后五款车接口全部 200、日志无 traceback；E2E 切换钛3 无异常 | `logs/web-service-20261109.log` |
| S10 | 方案 A：购车关注措辞与空态卡 | 完成 | 标题/副标题写明「16 维多选勾选率（非首选率）」；空态卡补齐指标名，标注「首选率 · 待业务补排序题，不估算、不填 0」；后端与指标未改 | `bci-analysis.js`、`bci-analysis.css`、`e2e_analysis_page.py` |

## 4. 证据索引

- 可行性测评证据：`outputs/competitor-insights/BCI-006/20261107-feasibility/`（`manifest.json`、`README.md`、`four_source_counts.csv`）
- 实现与验收证据：`outputs/competitor-insights/BCI-006/20261107-analysis/`
  - `manifest.json`：证据用途、复现命令、清理条件
  - `metrics_summary.json`：五款车四磁贴关键实测数字（比例 + 分子/分母）
  - `screenshots/`：B10 整页/视口/四磁贴、钛3 整页
- 浏览器与接口断言脚本：`competitor_insight/tests/e2e_analysis_page.py`、`e2e_analysis_api.py`、`test_analysis_service.py`
- 只读探查脚本：`temp/20261107-bci006/`（probe_data*.py、probe_align.py、probe_names.py、probe_candidates.py、probe_size.py、probe_five.py、probe_bases.py、probe_proto.py、probe_price.py、probe_pool.py；可清理，结论已固化到测评文档）
- 候选池四源明细：`temp/20261107-bci006/pool.csv`

## 5. 已知边界（不是缺陷，但下游必须知道）

- 入选五款每款定量 30–41 人、深访 3–4 人，属小样本；比例不可外推到细分市场。
- 更正：`601/1380`、`521/1380` 是单个选项已选人数；`Q3_13`/`Q3_23`/`Q3_24_1` 的 16 键并集作答均为 1380/1380，五款车型也等于各自总样本。
- 勾选率分母为车型定量总样本，页面同时给分子/分母与「实际作答 n/总样本」。
- 库内无车型级别字段，「10–15 万 SUV」为公开定位推断，需业务确认。
- 口碑为外部评论标签，与问卷满意度不同源，不合并成单一分数。
- 「战败」只能定义为「放弃核心对比车型的原因」（Q3_24_1），不是双边市场口径；本库无未购车用户样本。
- 原型五车三项关键数据为零，不能作为默认车型。

## 6. 遗留问题

| 编号 | 问题 | 影响 | 现状 | 解除条件 | 负责人 | 证据/关联 |
|---|---|---|---|---|---|---|
| BCI-006-L01 | 关注「第一排序」结构无题项 | 原型「产品/品牌/服务 占比」不可复刻 | 已确认 `quant_question` 中「排序」0 条 | 业务补排序题或确认改用多选勾选率 | 业务 | 测评 §3 |
| BCI-006-L02 | ~~`Q5_5` 推荐意愿 0 条作答~~ | 已更正视作可做 | 文本分值 100% 有作答，已实现均值/分档 | 已解除 | TRAE | 测评 §11 C1 |
| BCI-006-L03 | 「对手为什么赢」无直接观测题 | 只能推断 | 页面空态 + 原因，v1 不做推断 | 业务提供未购车/流失用户样本或对手视角题 | 业务 | 测评 §4 |
| BCI-006-L04 | 车型名称多源不一致（iCAR 超级V23 / 奇瑞iCAR V23；MG 07 / MG07；小鹏MONA M03 / 小鹏M03） | 跨源计数易错 | 已落地 `config/analysis_models.json` 别名并有单测 | 已解除 | TRAE | 测评 §1.2、§5 |
| BCI-006-L05 | 车型级别/车身形式库内无字段 | 「同级对比」只能按价格段 | 已标注为推断 | 业务确认级别口径或补数据 | 业务 | 测评 §1.2 |
| BCI-006-L06 | 定性 16 维归类为关键词启发式 | 个别原话可能漏归或误归 | 未命中原话单列展示，不强行匹配 | 后续可接语义模型或人工校对；当前不改判实测比例 | TRAE/业务 | 测评 §11 C4 |
| BCI-006-L07 | 满意度「本品进攻点 / 被进攻点」需跨车差值 | v1 未做 | 页面不出现该图，避免小样本推导冒充实测 | 业务确认接受「推导」标记与对比车选择规则 | 业务 | 测评 §5 |
| BCI-006-L08 | 「分车型关注 TOP5」口径待定：业务希望按 63 位深访用户各自车型做关注 TOP5 | 深访 3–4 人与定量 30–41 人不是同一口径，不能混排 | **暂停**：2026-11-09 用户决定分车型 TOP5 与首选率都先不做，拿口径与业务商量；页面不加深访视图，首选率维持现有空态卡，A 方案文案不动 | 业务确认范围、并列规则与归类规则后再启动 | 业务/用户 | 本节探查结论；`temp/20261109-bci006-qual/` |

- BCI-006-L08 口径差别：**定量口径**按车型定量总样本（五款 n=30~41）算 16 维勾选率，可出分子/分母与比例；**深访口径**把 63 人深访名单按车型分组（每车 3–4 人），只能出「提及人数 / 该车深访人数」，是线索不是比例，不能与定量数据混排或合并。
- 探查依据（只读，2026-11-09）：
  1. 63 人分布：现有五款车合计 16 人（B10 4、铂智3X 3、海狮05 EV 3、钛3 3、iCAR V23 3＝奇瑞 2＋iCAR 1 按别名合并）；其余 47 人分布在 16 个车型（6 款各 4 人、4 款各 3 人、5 款各 2 人、1 款 1 人），单车型 1–2 人时 TOP5 无区分度。
  2. 候选题：**Q20**「用户购车时关注哪些方面？给出排序TOP5…」是唯一直接问购车关注的题（63/63 有答）；Q21 含“上次购车”不能与 Q20 混计；Q46 是实际用车关注；Q4/Q29 是购车/选择原因，不是关注要素。
  3. 归类：复用 `tag_dimensions` 同一套 16 维与关键词做确定性匹配，未命中原话单列；16 人 Q20 全部至少命中 1 维（完全未归类 0 人）。已知偏差：否定句被计入（铂智 R048 说智驾“并非重点”仍归入智能驾驶）、同义词漏计（“省钱/节能”未命中使用费用、“通过性”未命中 16 维）。
  4. 关键词结果（≥2 人，提及人数/该车深访人数）：B10 外观 4/4、续航 4/4、空间 2/4、内饰 2/4、价格 2/4、品牌 2/4；iCAR 外观 3/3、空间 2/3；海狮 外观 2/3、价格 2/3；钛3 空间 3/3、内饰 2/3、外观 2/3、安全 2/3；铂智3X 品牌 3/3、空间 2/3、质量 2/3、智能座舱 2/3。
  5. 启动前待业务确认：范围为五款车 16 人还是全部 63 人/22 车型；TOP5 并列规则（只列 ≥2 人还是强行取满 5 项并标并列）；是否允许本视图用独立确定性映射处理否定句与同义词（不改战胜战败共享关键词）。
- 证据：`temp/20261109-bci006-qual/`（`probe_qual.py`、`probe_qual_questions.py`、`probe_q20.py`、`q20_report.txt`）；本轮未改任何页面代码。

**入库判定边界**：`app.py` 同时承载另一条线（深度调研）的在途改动，`check_board.py` 的 `TASK-COMMITTED` 无法区分 hunk。本任务只把 4 处 BCI-006 片段（全局单例、`bci_analysis_service()`、路由分派、`_handle_bci_analysis_get`）写入索引，因此 `commit_paths` 不声明 `app.py`，与 BCI-001 对共享文件的处理一致；每次改动需人工核对 `git diff --cached -- app.py` 仅含 BCI 片段。`BOARD.md`、`HANDOFF.md`、`tasks/tasks.md` 是多任务共用状态文件，同样不声明，避免其他任务在途改动按文件级状态把本任务误判为未入库。`home.html` 与 `web/bci.js` 本次改动全部属于 BCI-006，仍按声明校验。

## 7. 阶段流转记录

| 日期 | 阶段 | 依据 | 证据 | 变更人 |
|---|---|---|---|---|
| 2026-11-07 | CREATED | 用户明确要求先做可行性测评并建 BCI-006；S1/S2 完成，代码未开始 | `outputs/competitor-insights/BCI-006/20261107-feasibility/manifest.json` | TRAE |
| 2026-11-07 | EXECUTING | 用户确认五款 SUV 与 Q1/Q29/Q27/Q28 口径；S3–S6 实现与三类验收通过 | `competitor_insight/tests/`、`outputs/.../20261107-analysis/` | TRAE |
| 2026-11-07 | TESTED | 浏览器端到端验收通过；五车实测数字与数据缺失清单归档；代码与证据已提交 `5e8f964`、文档 `ca18f37`，均已推送（本地 HEAD 与 `@{u}` 均为 `6775c56`，`@{u}..HEAD` 为 0），待用户业务验收 | `outputs/.../20261107-analysis/manifest.json` | TRAE |
| 2026-11-09 | TESTED | 用户核对后要求四子功能改为入口卡片展开/收起；已完成并重跑浏览器 E2E（37 项全通过，含默认展开、多选叠加、选中顺序、收起不占版面）；同时定位「换车型查询失败」为服务被回收的连接层问题，服务改为 WMI 脱离终端启动；提交 `93ce621` 已推送 | `tests/e2e_analysis_page.py`、`screenshots/analysis-b10-entries-20261109-181238.png` | TRAE |
| 2026-11-09 | TESTED | 方案 A 文案上线（购车关注标「非首选率」、首选率空态补指标名与待补排序题说明，E2E 42 项全通过，`a0f9ebc` 已推送）；L08 深访口径 TOP5 经用户决定暂不实现并暂停，探查依据入档 | `screenshots/tile-2-b10-20261109-193324.png`、本节 L08 | TRAE |

## 8. 因数据缺失而未做的指标（可对外说明）

| # | 指标 | 页面处理 | 具体原因 | 补齐条件 |
|---|---|---|---|---|
| 1 | 购车关注「产品 / 品牌 / 服务 第一排序」 | 空态卡片 | `quant_question` 无排序题；`Q3_13` 为多选勾选，无排序权重 | 业务补排序题或确认改用 16 维勾选率 |
| 2 | 对手为什么赢 / 竞品胜出逻辑 | 空态卡片 | 库内无对手视角观测题；本库全部为已购车用户，无未购车/流失样本 | 补未购车样本或竞品侧题项 |
| 3 | 本品进攻点 / 被进攻点 | 不展示 | 需跨车满意度差值推导，单维样本小，易被误读为实测 | 业务确认推导口径与对比车规则 |
| 4 | 生活状态分型占比 | 只出逐人原话 | 每车深访 3–4 人，无分型标签题；出比例会误导 | 扩大深访样本或补标签题 |
| 5 | 定性原因的「为什么」强度 | 只出原话，不出比例 | 深访人数 3–4 人，页面明确标人数 | 扩大深访样本 |

## 9. 运行与排查说明

- 用户 2026-11-09 明确：7860 **不做开机自启**，不注册计划任务，维持手动启动。
- 机器重启或服务被回收后，需手动用 `start_agent.cmd` 拉起，再访问页面。
- 排查提示：页面能打开、但「即时分析」报「查询失败 / Failed to fetch」且四个来源计数为 0，多半是 7860 服务没起（连接层失败），不是接口口径或数据问题；先确认服务在听、用 `GET /api/bci/analysis/models` 直连验证，再查页面缓存（资源版本号 `v=20261109`）。
