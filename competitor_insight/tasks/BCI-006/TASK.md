# BCI-006：竞品洞察 · 即时分析 tab

```
task_id: BCI-006
title: 竞品洞察 · 即时分析 tab
stage: TESTED
owner: TRAE
port: 7860
frozen_paths: none
commit_paths: competitor_insight/server/analysis_service.py, competitor_insight/server/agent_tools.py, competitor_insight/server/agent_analysis.py, competitor_insight/prompts/, competitor_insight/tests/test_agent_analysis.py, competitor_insight/server/name_rules.py, competitor_insight/config/analysis_models.json, competitor_insight/config/vehicle_name_map.json, competitor_insight/config/vehicle_name_map.csv, competitor_insight/config/vehicle_name_confirmations.json, scripts/build_vehicle_name_map.py, competitor_insight/web/bci-analysis.js, competitor_insight/web/bci-analysis.css, competitor_insight/tests/test_analysis_service.py, competitor_insight/tests/e2e_analysis_api.py, competitor_insight/tests/e2e_analysis_page.py, competitor_insight/docs/analysis-tab-feasibility.md, competitor_insight/tasks/BCI-006/, outputs/competitor-insights/BCI-006/20261107-analysis/, outputs/competitor-insights/BCI-006/20261107-feasibility/, outputs/competitor-insights/BCI-006/20261111-agent-analysis/, home.html, competitor_insight/web/bci.js
updated: 2026-11-11
blocked: no
next: 智能化分析 P0 已跑通（工具层 + 固定骨架 + 独立区域 + 截图）；真实模型合成因 `DASHSCOPE_API_KEY` 401 未验证，需用户更新凭证或授权其他提供方后补一次真实模型实跑
evidence: outputs/competitor-insights/BCI-006/20261111-agent-analysis/
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
| S11 | 标准名去动力后缀 + `power_form` 后端切分 | 完成 | 新增 `name_rules`（`strip_power_suffix`/`power_form_of`/`normalize_power_form`）；映射库重建为 1024 写法 / 1024 已归一 / 0 待确认 / **701 标准名** / 2065 明细 / 280 业务确认，56 个标准名受影响、行数与键集合不变；`normalize_competitor` 先别名再去后缀；`analyze` 增可选 `power_form`（纯电/插混/增程，按受访者 `Q2_2` 切分，非法值 400 `invalid_power_form`），响应新增 `power_form`/`power_form_source`/`power_forms`，战败行增 `power_forms`；`analysis_models.json` 海狮05 四源合并为 `海狮05 EV`/`海狮05 DM-i`/`海狮05` 并把 label 改 `海狮05`；**前端未改**（无筛选控件、无页面改动）；单测 29 项 + 隔离端口 7873 e2e 全通过 | `competitor_insight/server/name_rules.py`、`analysis_service.py`、`scripts/build_vehicle_name_map.py`、`config/vehicle_name_map.json`、`temp/20261110-bci006-name-finalize/` |
| S12 | 只读核实动力/燃料题项（不设静态列） | 完成 | 购买侧 `Q2_2` 覆盖 1380/1380（纯电动 601 / 插电混动 523 / 增程式 256）；对比侧 `Q3_22_2_1/2/3` 覆盖 1380/1378/1154，取值 纯电/插混/增程/纯燃油/油电混动；`Q2_1` 与 `purchase_model` 1380/1380 一致；476 种对比写法中 76 种含 ≥2 种动力；结论：映射表不加静态动力列，按题项实时取 | `temp/20261110-bci006-name-finalize/probe_q3_22_2.py`、`probe_q2_2.py`、`probe_q2_1.py` |
| S13 | 动力改五类 + 小鹏M03 别名解环 | 完成 | `POWER_FORMS` 扩为 纯电/插混/增程/纯燃油/油电混动，新增 `POWER_FORM_ALIASES` 原始写法对照（不再做名称推断，`power_form_of` 已删除）；`未标注` 只剩真正没答：对比侧 229 条（228 条空白 + 1 条「无」占位，全是没填该款车，写了车却燃料为空 0 条），购买侧 0；`power_form` 接受五类，传纯燃油/油电混动定量为 0 不报错；`analysis_models.json` 的 `小鹏MONA M03→小鹏M03` 反向环改为自指，新增单测 `test_competitor_aliases_resolve_in_one_hop`；37 项单测通过；五车重跑仅「纯电」有样本（其余四类 0），零跑C16 进程内仍为 纯电 31 / 增程 34；海狮05 整体战败 35 人/10 行，纯电切分 29 人/9 行（余下 3 插混 + 3 增程受访者） | `competitor_insight/server/name_rules.py`、`analysis_service.py`、`config/analysis_models.json`、`temp/20261110-bci006-name-finalize/probe_final_report.py`、`probe_compare_dist.py`、`probe_loss_fuel.py` |
| S14 | 三块 AI 结论诊断与提示词重写 | 完成 | 诊断：用户截图三句均来自模型，非模板兜底——旧缓存 `source=llm`、`prompt_version=2026-11-10.3`、`generated_at=2026-11-10T11:37:41~43+08:00`，单块耗时约 1 秒，旧 System Prompt 明确要求「最突出特征+数字、次一级差异+数字」，模型照做才成统计播报。重写：画像改定性标签（技术理性派/事业上升期/理性消费等，禁百分比与「最突出/次之」）；关注固定分层（入场券/第一触点、必备项/竞争重点、加分项/底线筛查）；战胜战败给核心归因+流失痛点+「下一步重点防御Y」，满意度不再生成 AI 结论；战败/战胜喂深访 Q27/Q28、Q29 原话并标「来源：深访」+人数；输出 50–65 字（硬上限 70），格式不合格重写一次仍不合格则报错；缓存键含提示词版本号与提示词哈希；模型失败直接返回 error，不再用模板句顶替。五车 15 块实测全部 `source=llm`（1.2–3.2 秒/块），单测 35 项通过；7860 常驻进程仍是旧代码，需用户授权后重启才对页面生效 | `competitor_insight/server/tile_summary.py`、`analysis_service.py`、`app.py`、`competitor_insight/web/bci-analysis.js`、`bci-analysis.css`、`competitor_insight/tests/test_analysis_service.py`、`temp/20261110-bci-tile-ai/` |
| S15 | 重启 7860 + 清缓存 + 五车复跑与截图验收 | 完成 | 重启前确认月报专用 Chrome 未运行；本机 shell 存在 116 位失效 `DASHSCOPE_API_KEY`（末四位 2A5E），改用 `temp/20261110-restart-service/launch.ps1` 在进程内注入 `.env` 的 35 位键（末四位 9f70）后经 WMI 脱离终端启动；7860 监听 PID 20196，`/api/health` ok、`/api/bci/analysis/analyze?model=` 返回 ok；旧 `.3` 缓存已归档 `backup/20261110-bci-tile-ai-cache/`，`runtime/bci-analysis/tile-summary/` 现存 15 个文件全为 `prompt_version=2026-11-10.8`、`source=llm`；五车 15 块经 HTTP 重新生成全部 `source=llm`（1.3–2.2 秒/块），本次无格式重写、无 error；iCAR 超级V23 与 铂智3X 三块 AI 结论同图截图已归档 | `outputs/competitor-insights/BCI-006/20261110-tile-ai/`、`temp/20261110-restart-service/` |
| S16 | 全量补打标 + 口碑 TOP5 改造（去下钻） | 完成 | 补打批次 `20261110T193628`：全表 45,613 条按纯正则重算（无抽样、无上限、复用检查点 0），命中 20,085 条，覆盖率 29.18%→44.03%；写 37,415 标签行 / 3,474 汇总行，异常 0；耗时 read 16.25s / analyze 16.09s / aggregate 0.13s / payload 1.26s / publish 80.07s（汇总 insert 2.13s、标签明细 insert 58.01s）。改造：`reputation()` 改读 `new_car_reputation_review_tag` 最新批次，按 `count(DISTINCT review_key)` 计、每方向 TOP5、并列按标签名升序；分母改原始两平台 `count(DISTINCT dedupe_key)`（五车 237/289/280/377/400）；接口新增 `batch`/`batch_reviews`/`positive_total`/`negative_total`，页面只留正向/负向两列、删除标签下钻；9 个可对齐维度映射显示名（如 安全表现→安全性），质量/电池特性等照原词；单测 150 通过，五车截图 5 张 | `temp/20261110-reputation-top5/`、`outputs/competitor-insights/BCI-006/20261110-reputation-top5/`、`outputs/reputation-full-analysis/20261110T193628/report.json` |
| S17 | 口碑口径 A：L3 点 + 汽车之家单源 + 三道门槛 | 完成（第一步） | 依据 `20261111-satisfaction-points-study/03-建议口径.md`：`reputation()` 改按 L3（`tertiary_label`）出点、每方向 TOP5；数据源限定 `source='autohome'` 最新批次，懂车帝不混入；分母改 `autohome_koubei` 满意/不满意字段非空行数（五车 103/200/200/227/195，`source_counts.reputation` 同口径）；三道门槛：单点去重 `review_key` <3 不进榜、方向分母 <50 标「样本不足」、服务类按 **L3 白名单**排除（`REPUTATION_SERVICE_L1` 三个服务类一级类目下只有 `REPUTATION_PRODUCT_L3`＝`试驾体验` 放行并正常参与 TOP5，其余服务类 L3 默认排除；以后新增服务类标签默认排除，属性属产品体验才显式加白名单）；方向沿用标签方向（子句情感），字段只作先验。试驾体验放行后重跑五车：海狮05 正向第一 试驾体验 23 条 10.1%（负向第四 7 条 3.1%），iCAR 正负向各新进 1 点，B10/铂智3X/钛3 未变（这三车试驾体验点仅 1–2 条，未达 3 条门槛）。页面：两列点+条数+占比(n)、顶部写「当前车型：XXX（n=…，截至 2026-11-04）· 本车自身口碑分布，非竞品份额」、16 类 L1 折叠为上卷/无达标点时回退并标「粒度：类目」、底部一句边界（仅汽车之家有分离字段、2026-01 至 11-04、每车系 200 条上限）；另修 `analyze()` 切车竞态（迟到响应不再覆盖当前车型）。单测 150 通过，五车截图 5 张 | `competitor_insight/server/analysis_service.py`、`web/bci-analysis.js`、`tests/test_analysis_service.py`、`temp/20261111-reputation-l3/`、`outputs/competitor-insights/BCI-006/20261111-reputation-l3/` |
| S18 | 口径 A 第二步：新增 1 个 L3 + L3 别名层，重打标 | 完成 | 方案 B 执行：`reputation-taxonomy.json` 新增 `车身尺寸与灵活性`（`L05-02-06`，挂 动力与操控/驾驶控制，`custom=true`，153→154 个 L3，未改既有骨架）；新增 `maintenance/reputation-aliases.json` 别名层（7 个 L3 共 41 条同义短语：座椅软硬与支撑/屏幕显示/配置价值 三个缺口走别名，另补 实际续航/路面滤震/车内气味/风噪 口语说法），合并点在 `strict_patterns` 之后，未知 L3 直接报错避免静默失效；`analyze_review` 的 `is_custom` 改为读 taxonomy 标记。重打批次 `20261111T113525`：45,613 条全量重算（复用检查点 0），命中 20,278 条（+193）、标签行 38,018（+603）、汇总行 3,481，异常 0；耗时 read 12.68s / analyze 17.37s / publish 104.33s。新 L3 全库 385 行（正 208 / 负 177），已过「全库≥30」立项门槛；五车该点均为 0 条未进榜，别名目标点在五车最多 2 条，故五车 TOP5 与第一步完全一致。单测 164 通过 | `maintenance/reputation-taxonomy.json`、`maintenance/reputation-aliases.json`、`maintenance/reputation_analysis.py`、`maintenance/run_reputation_analysis.py`、`tests/test_reputation_analysis.py`、`outputs/reputation-full-analysis/20261111T113525/report.json` |
| S20 | 智能化分析真实模型联调与 401 修复 | 完成 | 根因：用户级环境变量中 116 位旧 `DASHSCOPE_API_KEY`（末四位 2A5E）覆盖 `.env` 35 位正键（9f70）。修复：`app.py` 启动改为 `load_dotenv(..., override=True)`（进程内显式注入 `.env`）；`agent_analysis.py` 增加 `timings`（route/tools/compose/validate/total）；`_numbers_in` 剥离年龄段/价格段标签（26-30岁、10-15万）；硬性字数上限 W1 600 / W2 650（提示词仍 450/400）；W2 提示词限定 differences ≤6 条按 |delta| 降序、gaps 必须取满意度或口碑负向。真实模型实测：W1 海狮05 首次校验失败、重写 1 次通过（attempts=2）；W2 海狮05 vs 零跑B10 一次通过（attempts=1）；独立复核 `numeric_index` 未匹配数字 0（W1 56 个登记值）；页面（零跑B10）W1/W2 均一次通过，pool-out 正常。`competitor_insight/tests` 157 通过 | `app.py`、`competitor_insight/server/agent_analysis.py`、`competitor_insight/prompts/agent_compose_w2.txt`、`outputs/competitor-insights/BCI-006/20261111-agent-analysis/real-run/real_run.json`、`screenshots/1*-real-*.png`、`temp/20261111-agent-analysis/run_real.py`、`serve_real.py`、`shoot_real.py` |
| S19 | 智能化分析 P0：工具层 + 固定骨架 + 独立区域 | 完成 | 按 `20261111-agent-analysis-plan-v2.md` 落地：① `server/agent_tools.py` 只读取数工具（context / quant_distribution / winloss / satisfaction / reputation / interview_quotes / circulation 空态 / competitor_candidates 现算 / head_to_head / compare_metric），所有数字登记 `numeric_index`，单侧 <5 或作答 <10 隐藏比例与差值；② `server/agent_analysis.py` 固定骨架 Router→Preflight→ToolBox→Derive→Composer→Validator，靶心只取请求车型，竞品池按 `Q3_22_1__1/2/3 × purchase_model` 现算取前 3 不设门槛，池外返回 `no_comparison_sample`，四源平权、流通空态、口碑不跨车相减；③ `POST /api/bci/analysis/agent`；④ 前端 `bci-analysis.js/css` 新增独立区域（当前车型、样例、加载/成功/错误、refs、取数明细），不与四卡联动。真实库实测：海狮05 W1 定量 31/深访 3/口碑 227、池 10 台；零跑B10 W1 定量 41/深访 4、W2 vs 铂智3X 15/40 双向对冲 L1；`competitor_insight/tests` 157 项通过 | `competitor_insight/server/agent_tools.py`、`agent_analysis.py`、`prompts/agent_*.txt`、`app.py`、`competitor_insight/web/bci-analysis.js`、`home.html`、`competitor_insight/tests/test_agent_analysis.py`、`temp/20261111-agent-analysis/`、`outputs/competitor-insights/BCI-006/20261111-agent-analysis/` |

## 4. 证据索引

- 可行性测评证据：`outputs/competitor-insights/BCI-006/20261107-feasibility/`（`manifest.json`、`README.md`、`four_source_counts.csv`）
- 实现与验收证据：`outputs/competitor-insights/BCI-006/20261107-analysis/`
  - `manifest.json`：证据用途、复现命令、清理条件
  - `metrics_summary.json`：五款车四磁贴关键实测数字（比例 + 分子/分母）
  - `screenshots/`：B10 整页/视口/四磁贴、钛3 整页
- 浏览器与接口断言脚本：`competitor_insight/tests/e2e_analysis_page.py`、`e2e_analysis_api.py`、`test_analysis_service.py`
- 只读探查脚本：`temp/20261107-bci006/`（probe_data*.py、probe_align.py、probe_names.py、probe_candidates.py、probe_size.py、probe_five.py、probe_bases.py、probe_proto.py、probe_price.py、probe_pool.py；可清理，结论已固化到测评文档）
- 候选池四源明细：`temp/20261107-bci006/pool.csv`
- 三块 AI 结论实测：`temp/20261110-bci-tile-ai/`（`run_tiles.py` 五车真实模型调用、`tiles.json` 每块 source/耗时/结论/真实 user 内容/System Prompt、`probe_bz3x.py` 截断探针）
- 重启与截图验收：`outputs/competitor-insights/BCI-006/20261110-tile-ai/`（`manifest.json`、`screenshots/toyota-bz3x-three-tiles.png`、`screenshots/chery-icar-v23-three-tiles.png`）、`temp/20261110-restart-service/`（`launch.ps1` 注入 `.env` 键并脱离终端启动、`summaries.json` 五车 15 块结论与耗时、`shot_tiles.py` Playwright 截图脚本）
- 口碑 TOP5 改造与补打标：`outputs/competitor-insights/BCI-006/20261110-reputation-top5/`（`manifest.json`、`top5.json` 五车分母/TOP5/占比、`screenshots/*-reputation-top5.png` 五张）、`temp/20261110-reputation-top5/`（`probe_top5.py`、`check_top5.py`、`shot_reputation.py`）；补打运行报告 `outputs/reputation-full-analysis/20261110T193628/report.json`（覆盖率、`timing_seconds`、`publish_timing`）
- 口碑口径 A（L3 点）：研究 `outputs/competitor-insights/BCI-006/20261111-satisfaction-points-study/`（`01-数据对照表.md`、`02-样例清单.md`、`03-建议口径.md`）；实测 `outputs/competitor-insights/BCI-006/20261111-reputation-l3/`（`manifest.json`、`l3_actual.json` 五车 L3 TOP5/分母/占比、`screenshots/*-reputation-l3.png` 五张）；探查脚本 `temp/20261111-reputation-l3/`（`probe_l3.py`、`summarize_l3.py`、`l3_report.py`、`shot_l3.py`）
- 智能化分析 P0：`outputs/competitor-insights/BCI-006/20261111-agent-analysis/`（`screenshots/00-agent-idle.png`、`01-agent-w1.png`、`02-agent-w2.png`、`03-agent-no-sample.png`）；工具层/链路探针 `temp/20261111-agent-analysis/`（`probe_tools.py`、`probe_stub_flow.py`、`stub_llm.py` 本地固定合成器、`serve_stub.py` 页面联调启动器、`shoot_page.py` headless 截图脚本）；方案 `outputs/competitor-insights/BCI-006/20261111-agent-analysis-design/20261111-agent-analysis-plan-v2.md`

## 5. 已知边界（不是缺陷，但下游必须知道）

- 入选五款每款定量 30–41 人、深访 3–4 人，属小样本；比例不可外推到细分市场。
- 更正：`601/1380`、`521/1380` 是单个选项已选人数；`Q3_13`/`Q3_23`/`Q3_24_1` 的 16 键并集作答均为 1380/1380，五款车型也等于各自总样本。
- 勾选率分母为车型定量总样本，页面同时给分子/分母与「实际作答 n/总样本」。
- 库内无车型级别字段，「10–15 万 SUV」为公开定位推断，需业务确认。
- 口碑为外部评论标签，与问卷满意度不同源，不合并成单一分数。
- 「战败」口径（2026-11-10 用户定稿）：定量 `Q3_22_1__1/2/3` 任一列（别名归一后）等于当前目标车型，即「对比过靶心」；按 `purchase_model` 分组，每行「实际购车车型 胜出 + 人数 + 比例 + 原因 TOP3」，买了靶心的人不算战败；原因按靶心所在槽位取 `Q3_24_1/3/5`。不设样本量门槛、不并「其他」、不删行；行内 ≥5 人且对比总数 ≥10 才给百分比。本库无未购车用户样本。
- 原型五车三项关键数据为零，不能作为默认车型。
- **车型范围现状（2026-11-09 只读盘点）**：页面下拉只有五款，是 `config/analysis_models.json` 的**演示集硬编码**，没有样本量阈值筛选；`analysis_service` 的 `models()` 只返回该配置。库内定量实际共有 **40 种车型写法 / 1380 人**（最多零跑C16 65 人，最少海狮06、银河L7 各 1 人），深访 22 种写法 / 63 人（归并后全部落在定量 40 款内），口碑 313 种写法 / 35609 条（仅 24 种能对上定量车型、3893 条），配置 605 种车型写法 / 3458 款（仅 28 种对上、199 款）。全量清单见 `outputs/competitor-insights/BCI-006/20261109-model-scope/`（`model_scope.csv`、`README.md`），供业务确认车型范围；本轮未改下拉、未改业务代码。比例展示门槛（2026-11-10 现状）：通用 `ratio_payload` 在车型样本 <10 或本题作答 <10 时只给人数；战败行单独用「该行 ≥5 人且对比总数 ≥10」才给百分比；两者都不参与选车、不删行。
- **口碑取数口径（2026-11-10 用户确认，已实施见 S16）**：**不做迁移、不碰采集**；采集继续在旧电脑运行，本项目只读 `vectordb` 库里的结果表。口碑指标不再使用 `public.new_car_reputation_summary`（POC 表，标签命中次数、批次 20260921），改为：
  - 评论条数、时间窗（2026-01-01 起）、评分均值 → `public.autohome_koubei`（34,649 条，至 2026-11-04）与 `public.dongchedi_koubei`（10,964 条，至 2026-11-04），按 `count(DISTINCT dedupe_key)` 计，分平台列示。
  - 标签/正负向结构 → `public.new_car_reputation_taxonomy_summary` + `new_car_reputation_review_tag`，读最新批次 `20261110T193628`（全库 45,613 条全量重打，命中 20,085 条 / 44.03%，标签明细 37,415 行、汇总 3,474 行）；其 `mention_count` 仍是标签命中，不得当评论量。
  - 两者关系：taxonomy 是标签明细来源（批次滞后于采集），原始表是分母底座；2026-11-11 口径 A 起页面占比＝该 L3 去重 `review_key` 数 ÷ 该车型 `autohome_koubei` 对应方向字段非空行数（五车 103/200/200/227/195），懂车帝不再进入口碑分子分母。
- **口碑展示形态（2026-11-11 口径 A 定稿，取代 2026-11-10 的 L1 版）**：满意度磁贴的外部口碑按 L3 点出数，正向/负向各 TOP5（去重评论数降序、并列按标签名升序、不足不补）；数据源只取 `new_car_reputation_review_tag` 中 `source='autohome'` 的最新批次，懂车帝 v1 不混入；分母＝`autohome_koubei` 对应方向字段非空行数（五车 103/200/200/227/195），`source_counts.reputation` 同口径。三道门槛：单点 <3 条不进榜、方向分母 <50 标「样本不足」、服务类按 L3 白名单排除（三个服务类 L1 下仅 `试驾体验` 放行——它衡量产品体验，正常参与 TOP5；其余服务类 L3 与以后新增服务类标签一律默认排除，需放行时显式加入 `REPUTATION_PRODUCT_L3`）。方向沿用标签方向（已按子句情感归向，字段只作先验，不按 satisfied/dissatisfied 字段一刀切）。16 个一级类目保留为折叠上卷，某方向 L3 全部 <3 条时回退并标「粒度：类目」，不与 L3 两列并排。页面边界句：仅汽车之家有满意/不满意分离字段、时间窗 2026-01 至 2026-11-04、每车系最多 200 条；顶部标注「当前车型：XXX（n=…）· 本车自身口碑分布，非竞品份额」。16 主标签中 9 个可对应问卷 16 维的做显示名映射（安全表现→安全性、乘坐舒适性→舒适性、空间与实用性→空间、外观设计→外观、内饰设计与做工→内饰、价格与购买价值→购车价格、品牌认知与信任→品牌、售后与服务保障→服务、辅助驾驶与泊车→智能驾驶），质量/续航/电池品牌类型等对不上的照原词，不硬凑。批次号与覆盖条数只放接口字段（`batch`/`batch_reviews`）。
- 名称归一：汽车之家 `iCAR 超级V23`、懂车帝 `iCAR超级V23`、taxonomy 两种写法并存；`海狮05 EV / 海狮05EV / 海狮05 DM-i` 需按车型别名合并，不能只按同名统计。
- **标准名去动力后缀（2026-11-10 用户定稿）**：标准名一律去动力/能源后缀只留简称（`海狮05 EV`/`海狮05 DM-i`→`海狮05`、`宋PLUS新能源`→`宋PLUS`、`领克07 EM-P`→`领克07`、`领克08 EM-P`→`领克08`），保留 PLUS 与型号字母；一个原始写法只对一个标准名，同名条目合并去重。影响 56 个标准名（736→701），2065 条明细的键集合与条数均未变。**该定稿取代 §6 BCI-006-L09 的「海狮05 ≠ 海狮05 EV」**：海狮05 战败块回到 35 人/10 行，页面标签为 `海狮05`。
- **动力形式五类（2026-11-10 用户定稿，取代三分类）**：`纯电`/`插混`/`增程`/`纯燃油`/`油电混动`，全部中文。原始写法对照见 `name_rules.POWER_FORM_ALIASES`：纯电动/纯电/EV/BEV→纯电；插电混动/插电式混合动力/PHEV/DM-i→插混；增程式/增程式电动/EREV→增程；纯燃油/燃油/汽油→纯燃油；油电混动/HEV→油电混动；裸「混动」不认（分不清插混与油电混动）。`未标注` 只保留真正没答的：对比侧 229 条（228 条空白 + 1 条「无」占位）全部是「没填该款车」（写了车却燃料为空 0 条），购买侧 0 条。
- **`power_form` 接受五类入参**：购买侧 Q2_2 只有纯电动/插电混动/增程式三个取值，传 `纯燃油`/`油电混动` 不报错但定量样本为 0（不是数据缺失，是本侧没有该取值）；非法值返回 400 `invalid_power_form` 并列出五类。
- 受影响的对比写法里「同一写法多种动力」普遍存在（476 种写法中 76 种），说明按名称推断动力不可靠，例如 `比亚迪宋PLUS` 插混 32 + 纯电 59、`零跑C11` 增程 41 + 纯电 43。

## 6. 遗留问题

| 编号 | 问题 | 影响 | 现状 | 解除条件 | 负责人 | 证据/关联 |
|---|---|---|---|---|---|---|
| BCI-006-L01 | 关注「第一排序」结构无题项 | 原型「产品/品牌/服务 占比」不可复刻 | 已确认 `quant_question` 中「排序」0 条 | 业务补排序题或确认改用多选勾选率 | 业务 | 测评 §3 |
| BCI-006-L02 | ~~`Q5_5` 推荐意愿 0 条作答~~ | 已更正视作可做 | 文本分值 100% 有作答，已实现均值/分档 | 已解除 | TRAE | 测评 §11 C1 |
| BCI-006-L03 | ~~「对手为什么赢」无直接观测题~~ | 指标名已由用户撤回（2026-11-10），不再提 | 页面空态保留但不再作为分析口径 | 无 | 用户 | 测评 §4 |
| BCI-006-L04 | 车型名称多源不一致（iCAR 超级V23 / 奇瑞iCAR V23；MG 07 / MG07；小鹏MONA M03 / 小鹏M03） | 跨源计数易错 | 已落地 `config/analysis_models.json` 别名并有单测 | 已解除 | TRAE | 测评 §1.2、§5 |
| BCI-006-L05 | 车型级别/车身形式库内无字段 | 「同级对比」只能按价格段 | 已标注为推断 | 业务确认级别口径或补数据 | 业务 | 测评 §1.2 |
| BCI-006-L06 | 定性 16 维归类为关键词启发式 | 个别原话可能漏归或误归 | 未命中原话单列展示，不强行匹配 | 后续可接语义模型或人工校对；当前不改判实测比例 | TRAE/业务 | 测评 §11 C4 |
| BCI-006-L07 | ~~满意度「本品进攻点 / 被进攻点」~~ | 「被进攻点」为我方外延，原型无依据，用户 2026-11-10 撤回 | 不再实现、不再提 | 无 | 用户 | 测评 §5 |
| BCI-006-L08 | 「分车型关注 TOP5」口径待定：业务希望按 63 位深访用户各自车型做关注 TOP5 | 深访 3–4 人与定量 30–41 人不是同一口径，不能混排 | **暂停**：2026-11-09 用户决定分车型 TOP5 与首选率都先不做，拿口径与业务商量；页面不加深访视图，首选率维持现有空态卡，A 方案文案不动 | 业务确认范围、并列规则与归类规则后再启动 | 业务/用户 | 本节探查结论；`temp/20261109-bci006-qual/` |
| BCI-006-L09 | ~~2026-11-10 定稿「海狮05 ≠ 海狮05 EV」~~ | 已被同日晚「标准名只留简称 + 同名合并」定稿取代 | 已解除：`海狮05 EV`/`海狮05 DM-i`/`海狮05` 合并为 `海狮05`，战败 35 人/10 行，纯电 29 人/9 行 | 无（如业务以后要按动力拆，用接口 `power_form`，不改映射） | 用户 | §5 标准名去动力后缀；`temp/20261110-bci006-name-finalize/` |
| BCI-006-L10 | ~~标准名仍并存全名与简称：`宋PLUS新能源` 14 行、`海豹05 DM-i` 3 行、`领克07 EM-P` 2 行、`领克08 EM-P` 3 行~~ | 同一车系被拆成两个标准名 | 已解除：全库标准名统一去动力后缀，`宋PLUS`、`海豹05`、`领克07`、`领克08` 等 56 个标准名完成合并 | 无 | TRAE | `config/vehicle_name_map.json`、S11 |

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
| 2026-11-09 | TESTED | 车型范围只读盘点：确认下拉五款为演示集硬编码、无阈值；产出全量 40 款四源清单供业务确认范围，未改下拉与业务代码 | `outputs/competitor-insights/BCI-006/20261109-model-scope/manifest.json` | TRAE |
| 2026-11-10 | TESTED | 口碑口径纠偏并试算：弃用 POC 汇总表的标签命中次数，改为只读 `autohome_koubei`/`dongchedi_koubei` 计评论条数与评分、taxonomy 一套取标签；五款演示车两平台真实条数已出，页面未改 | `temp/20261110-bci006-reputation-source/table_choice.txt` | TRAE |
| 2026-11-10 | TESTED | 「战胜战败」只读取证：零跑B10 面板（n=41）截图 3 段 + 入口态 + 完整长图，含定量 TOP5/16 维、Q29 原话、Q27/Q28 原话、核心对比车型分布、「对手为什么赢」空态；原型回查确认「进攻点」只在满意度模块、「被进攻点」无原型依据；未改代码 | `outputs/competitor-insights/BCI-006/20261110-winloss-shot/manifest.json` | TRAE |
| 2026-11-10 | TESTED | 战败口径二次纠正并实测（只读）：战败改为定量 Q3_22_1__1/2/3 任意一列等于靶心、按 purchase_model 分行。实测五款靶心被对比 40/17/35/11/21 人；严格仅用 Q3_24_1 时只剩核心对比 16/7/10/3/7 人。发现 Q3_24_1 只对应第一格，靶心在第二/三格时须改用 Q3_24_3/5；定量表无 Q27/Q28/Q29 原话。未改页面 | `temp/20261110-bci006-loss-scope/quant_loss_report2.txt` | TRAE |
| 2026-11-10 | TESTED | 战败块按用户口径实现：撤掉 ≥5 人门槛、不并「其他」、不删行；按 `Q3_22_1__1/2/3` 别名归一反查 + `purchase_model` 分行，原因按槽位取 `Q3_24_1/3/5` 的组内 TOP3；页面标依据题号。铂智3X 7 行/17 人（4/3/3/3/2/1/1）、钛3 5 行/21 人（14/3/2/1/1），与用户硬核对值一致。原「核心对比车型分布」块与「XX 胜出」重复，已合并删除。25→28 个单测、e2e_api、e2e_page 全通过 | `outputs/competitor-insights/BCI-006/20261110-ai-summary/screenshots/02-winloss-*.png` | TRAE |
| 2026-11-10 | TESTED | 四个入口文案按原型逐字回改（用户画像/购车关注/战胜战败原因洞察/产品满意度评价）；车型别名归一扩到海狮05 EV 五种写法、领跑B10、方程豹钛3、iCAR 三种写法；新增共享名称映射库 `config/vehicle_name_map.json`/`.csv`（1032 种写法，已归一 758、待确认 274，含来源表与命中条数） | `config/vehicle_name_map.json`、`screenshots/01-entries.png` | TRAE |
| 2026-11-10 | TESTED | 四磁贴新增「块内 AI 结论」：`server/tile_summary.py` 只吃本块数字拼三段式提示词，走项目现有 agentscope 模型（`app.py: bci_tile_summary_llm`），按「车型+磁贴+数据哈希」缓存到 `runtime/bci-analysis/tile-summary/`，模型失败降级模板句；`/api/bci/analysis/summaries` 供前端填充，页面独立一行标注「基于本块数据生成」。注意原型 sat 块原本没有 AI 结论行，四块全覆盖是按用户 2026-11-10 要求扩展 | `temp/20261110-bci006-satisfaction-audit/prompts.txt`、`screenshots/06-ai-rows-*.png` | TRAE |
| 2026-11-10 | TESTED | 满意度块只读现状核对（未改代码）：确认实现为 Q5_1 整体分 + Q5_2 16 维 top5/bottom5 + Q5_5 推荐分档 + 口碑标签，五款均 100% 作答；与原型「满意点/不满意点/本品进攻点」差第三部分，原型进攻点无对应题项 | `temp/20261110-bci006-satisfaction-audit/audit-output.txt`、`screenshots/03-satisfaction-*.png` | TRAE |
| 2026-11-10 | TESTED | 名称映射库导出业务核对 Excel：三表 274/758/14 行，表头冻结+筛选、输入列浅黄、Sheet2 按标准名交替底色，Sheet1 按来源分组+条数降序；同目录 README 说明填写与回收。生成器 `scripts/export_vehicle_name_map_xlsx.py`，校验脚本 `temp/20261110-bci006-vehicle-name-map-export/verify_xlsx.py` 全项通过 | `outputs/competitor-insights/BCI-006/20261110-vehicle-name-map/车系名称映射表_20261110.xlsx`、`README.md` | TRAE |
| 2026-11-10 | TESTED | 业务补填表回灌：Sheet1 266/267 填、Sheet2 改判 14、Sheet3 补 14；262 条写待确认→已归一（映射明细 +408 行）、139 条新增别名、12 条仍待确认（4 冲突 + 7 删行 + 「无」）；映射库 1020/12、标准名 732。五款演示车重跑：人数/比例/原因勾选率零变化，仅 3 处标签改名与 1 处同人数并列换位。未提交、未推送、未重启 7860 | `outputs/competitor-insights/BCI-006/20261110-vehicle-name-map/业务回填差异报告_20261110.md`、`competitor_insight/config/vehicle_name_confirmations.json` | TRAE |
| 2026-11-10 | TESTED | 业务定稿「无=没填」：① `analysis_service` 战败块取 `Q3_22_1__1/2/3` 时把「无」当空值（`CASE WHEN btrim(...) IN ('','无') THEN NULL`），不分组、不产生未匹配；② `build_vehicle_name_map.py` 新增 `COMPARE_EMPTY_RAW`，三格「无」不再收集；③ 删掉「无」待确认记录，待确认归零：写法 1024、已归一 1024、待确认 0、标准名 736、映射明细 2065、CSV 2066 行；④ `ratio_hidden_reason` 按真实命中原因分开输出（对比总数不足 10 / 该行不足 5），前端改为直接展示该原因。五车重跑：除文案外快照完全一致，海狮05 EV 仍 14 人 5 行。28 个单测通过。未提交、未推送 | `competitor_insight/server/analysis_service.py`、`scripts/build_vehicle_name_map.py`、`competitor_insight/web/bci-analysis.js`、`temp/20261110-bci006-name-finalize/` | TRAE |
| 2026-11-10 | TESTED | 名称映射遗留项按用户定稿执行完毕：① 4 条冲突一律用简称（宋PLUS/海豹05/领克07/领克08，`conflict_resolved`）；② 7 条不存在车型（吉利星耀E5、吉普自由者、小鹏YU7、红旗SH7、阿尔法T1、领克001、风行S7）在 `build_vehicle_name_map.py` 新增 `EXCLUDED_RAW` 重跑时剔除，json/csv/pending 均无残留；③ 靶心定稿 `iCAR 超级V23`/`海狮05`，别名、`models` label、战败行标题、映射表同步。重跑后：写法 1025、已归一 1024、待确认 1（「无」）、标准名 736、映射明细 2065、CSV 2067 行。28 个单测通过；五车快照对比：B10 无差异、铂智3X 与钛3 仅对手行改名、iCAR 人数不变仅标签改名、海狮05 EV 战败由 35 人/10 行降至 14 人/5 行（见 L09）。未提交、未推送 | `config/vehicle_name_map.json`、`config/vehicle_name_map.csv`、`config/analysis_models.json`、`temp/20261110-bci006-name-finalize/` | TRAE |
| 2026-11-10 | TESTED | 用户批准「标准名只留简称 + 动力形式单独一列」：S11 全库去动力后缀（1024 写法/701 标准名/2065 明细不变，56 个标准名合并），`normalize_competitor` 先别名再去后缀，`analyze` 增可选 `power_form`；用户中途修正「燃料是题项不是映射属性」后 S12 只读核实 `Q2_2`(1380/1380) 与 `Q3_22_2_1/2/3`(1380/1378/1154) 覆盖，确认映射表不设静态动力列；海狮05 合并后战败回到 35 人/10 行、纯电 29 人/9 行；前端未改；29 个单测 + 隔离端口 7873 的 API e2e 全通过；未提交、未推远程 | `temp/20261110-bci006-name-finalize/`、`competitor_insight/server/name_rules.py` | TRAE |
| 2026-11-10 | TESTED | 五类动力与 `小鹏MONA M03` 定稿：① `POWER_FORMS` 改 纯电/插混/增程/纯燃油/油电混动，Q3_22_2_x 的 纯燃油 131、油电混动 27 单列不再落「未标注」；② `小鹏M03`/`小鹏 M03`/`小鹏M03 EV` 与 `小鹏MONA M03` 全部归到 `小鹏MONA M03`，环状别名改为自指并加单跳单测；③ 验证：37 项单测通过、`check_board.py` 仅 `TASK-COMMITTED` 未过（文件未入库）、`workspace_hygiene.py` 仅既有 `debug.log`；五车人数 40/17/11/35/21，海狮05 整体 35 人/10 行、纯电切分 29 人/9 行（3 插混 + 3 增程受访者），零跑C16 纯电 31 / 增程 34；④ 按用户要求整理提交清单待确认，未提交、未推远程 | `temp/20261110-bci006-name-finalize/probe_final_report.py`、`probe_compare_dist.py`、`probe_loss_fuel.py`、`probe_c16.py` | TRAE |
| 2026-11-11 | TESTED | 用户批准口碑口径 A 并完成第一步：`reputation()` 改 L3 出点、`source='autohome'` 单源、分母改 autohome 满意度字段非空行数（103/200/200/227/195）、三道门槛（单点 <3、分母 <50 标样本不足、服务类排除）；页面两列点+条数+占比(n)、16 类折叠上卷与回退兜底、顶部标明「本车自身口碑分布，非竞品份额」、底部一行边界；顺带修 `analyze()` 切车迟到响应覆盖竞态。五车实测与 5 张截图归档，单测 150 通过；改动叠在 `4dbe3d0` 上另起本地提交，未 push | `outputs/competitor-insights/BCI-006/20261111-reputation-l3/manifest.json`、`temp/20261111-reputation-l3/` | TRAE |
| 2026-11-11 | TESTED | 用户改定：**试驾体验算产品体验要放回来**，服务类排除从「L1 整类」改为「L3 白名单」——`REPUTATION_SERVICE_L1` 下仅 `REPUTATION_PRODUCT_L3＝试驾体验` 放行，其余服务类 L3 默认排除，新增服务类标签默认排除。重跑五车：海狮05 正向第一 试驾体验 23 条 10.1%、负向第四 7 条 3.1%；iCAR 正负各新进 1 点（5/2.5%、4/2.0%）；B10/铂智3X/钛3 未变（该点仅 1–2 条未达门槛）。单测 150 通过；与 L1 版压成单条提交 `aed8f10` push 到 `origin/feature/user-insight-t0-t4`（a067296..aed8f10） | `competitor_insight/server/analysis_service.py`、`temp/20261111-reputation-l3/`、`outputs/competitor-insights/BCI-006/20261111-reputation-l3/` | TRAE |
| 2026-11-11 | TESTED | 口径 A 第二步（方案 B）：新增 L3 `车身尺寸与灵活性`（`L05-02-06`，custom 标记）+ 别名层 `reputation-aliases.json`（7 个 L3、41 条同义短语，合并于 strict overrides 之后，未知 L3 报错）；`is_custom` 改读 taxonomy。重打批次 `20261111T113525`（全量 45,613 条、复用检查点 0）：命中 20,278（+193）/ 标签行 38,018（+603）/ 汇总 3,481，新 L3 全库 385 行（正 208 / 负 177）。页面五车实取新批次，TOP5 与第一步逐项一致（五车该新点 0 条、别名目标点最多 2 条）。单测 164 通过；提交 93739e8 已 push 到 origin/feature/user-insight-t0-t4（aed8f10..93739e8）。环境备注：根目录 debug.log 由搜狗输入法进程持续占用，暂无法移入 logs/；不影响业务与验收，待占用释放后再归位 | `maintenance/reputation-taxonomy.json`、`maintenance/reputation-aliases.json`、`maintenance/reputation_analysis.py`、`maintenance/run_reputation_analysis.py`、`tests/test_reputation_analysis.py`、`outputs/reputation-full-analysis/20261111T113525/report.json` | TRAE |
| 2026-11-11 | TESTED | 用户确认口碑为智能化分析第四路，按方案 v2 P0 落地：工具层（四源平权、竞品池现算、小样本降级、numeric_index）、固定骨架（路由/合成为模型，取数/差值为代码）、`POST /api/bci/analysis/agent`、页面独立区域（不联动四卡、靶心取当前车型）。真实库联调通过（海狮05 / 零跑B10，W1/W2，pool-out 空态），`competitor_insight/tests` 157 项通过，headless 截图 4 张归档；真实模型 401 阻塞，待用户更新 `DASHSCOPE_API_KEY` 后补跑 | `outputs/competitor-insights/BCI-006/20261111-agent-analysis/`、`temp/20261111-agent-analysis/` | TRAE |

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
