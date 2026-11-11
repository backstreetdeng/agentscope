# BCI-007：竞品洞察 · 报告输出 tab

```
task_id: BCI-007
title: 竞品洞察 · 报告输出 tab
stage: TESTED
owner: TRAE
port: none
frozen_paths: none
commit_paths: competitor_insight/docs/report-output-design.md, competitor_insight/docs/report-output-business-inputs.md, competitor_insight/tasks/BCI-007, outputs/competitor-insights/BCI-007, competitor_insight/config/report_outline.json, competitor_insight/server/report_service.py, competitor_insight/server/report_archive_aggregate.py, competitor_insight/server/report_render_html.py, competitor_insight/server/report_api.py, competitor_insight/server/llm_client.py, competitor_insight/web/bci-report.js, competitor_insight/web/bci-report.css, competitor_insight/tests/test_report_service.py, competitor_insight/tests/test_report_render_html.py, ops/bci_report_ddl.sql, ops/apply_bci_report_ddl.py
updated: 2026-11-11
blocked: no
next: 用户验收 7860（一车一报告 / 11 页 / 页脚实时 n / 受控改稿 v1.1 / P7 进攻方向）；P6 首选率与 P9/P10 本品页待业务补样本或题项
evidence: outputs/competitor-insights/BCI-007/20261111-report-11p/
```

## 1. 目标与边界

- 目标：第三个 tab「报告输出」——基于洞察档案与即时分析结果，按标准化大纲生成用户洞察报告；先交付单文件 HTML（8 个页面单元），再交付 PPT（标准模板 → 业务模板）。
- 本轮（HTML v1）：大纲契约、档案聚合、报告服务、HTML 渲染、版本/失效、接口与 tab ④ 接入，全部落地并实测。
- 边界：
  - 报告主体为**竞品侧**，旧五车合报已转 `legacy` 只读；现固定一车一份，按 `model_key` 生成。
  - 原型 11 页全部保留（v2 大纲）：P02/P03（中汽换购）、P06（缺排序题口径）、P09/P10（缺本品样本）整页「暂未提供数据」并写缺口；页数不删、不用竞品数据顶替。
  - 标题照原型「序号-主题：一句结论」，结论由模型按本车数据生成并过数字校验，缺数据降级为只写主题。
  - 不做自由对话改稿；只开放 `set_title / limit_items / append_refs` 三种确定性改稿；PPT 入口本期不渲染。
  - 不发明库里没有的指标；无数据块显示「缺数据/样本不足」与原因，并进入附录缺口清单。
- 禁止项（已遵守）：未改 `bci` schema 属主；未改 `.gitignore`；未动其他任务文件；未重启 7860；未夹带其他业务线提交。

## 2. 验收标准与结果

| # | 验收项 | 判定方式 | 结果 |
|---|---|---|---|
| A1 | 8 个页面单元完整生成 | 生成 1 份 HTML，逐页对照大纲 | PASS：P01/P04/P05/P07/P08/P10/P11 + APPENDIX，`preview.html` 84,443 字节 |
| A2 | 每个数字可回溯，无硬编码 | 抽查数字指到 `analyze()` 字段或档案聚合；代码无写死车名/数字 | PASS：`report_service.py` 无车名硬编码；车型来自 `analysis_models.json`；单测 `test_labels_come_from_config_not_code` |
| A3 | 无数据页按契约不出 | P02/P03/P06/P09 不出现；附录列缺口与原因 | PASS：附录含缺口清单；`detail.gaps=1`（P04.BRAND_ROLE 无档案值） |
| A4 | 版本指纹与失效 | 同指纹复用；数据变化旧版标 stale 且仍可下载 | PASS：同指纹复用 v1（4.55s/5.23s）；`/detail` 返回 `stale:false`；stale 逻辑有单测 |
| A5 | PPT 导出与模板校验 | — | 延期（S5/S6，业务模板未提供） |
| A6 | 共用文件 hunk 归属清楚 | `git status` 只含本任务文件与登记的共享 hunk | PASS：`app.py` 仅 report 路由/处理器，`home.html` 仅 tab ④ 面板与引用，`bci.js` 仅 `initReport` |

## 3. 步骤与结果

| # | 步骤 | 状态 | 实际结果 | 证据 |
|---|---|---|---|---|
| S0 | 方案与业务待提供清单 | 完成 | `docs/report-output-design.md`、`docs/report-output-business-inputs.md`；python-pptx 能力边界实测 | `20261108-pptx-probe/` |
| S1 | 大纲与数据契约固化 | 完成 | `config/report_outline.json`（7 页 + 附录，块 `type/source/required`）；`report_service.py`；`report_archive_aggregate.py` 按车型收口 | `20261111-report-e2e/tests.log` |
| S2 | HTML 渲染与下载 | 完成 | `report_render_html.py`（单文件、无脚本/外链、全量转义）；`/preview`、`/export` 实测 200 | `preview.html`、`real_run.json` |
| S3 | 版本与失效 | 完成 | `ops/bci_report_ddl.sql` 已执行；`bci.report`/`bci.report_version` 就绪；同指纹复用不升版 | `20261111-report-ddl/apply.log` |
| S4 | 页面接入 | 完成 | `report_api.py` + `bci-report.js/css` + `app.py`/`home.html`/`bci.js` hunk | `screenshots/01-report-config.png` |
| S5 | 标准 PPT 模板导出 | 未做 | 二期；本期无 PPT 代码与入口 | — |
| S6 | 业务模板上传与占位符校验 | 阻塞 | 业务未提供 `.pptx` 模板 | — |
| S7 | 浏览器 E2E | 完成 | 7861 临时端口：tab ④ 可切、生成/复用文案正确、版本 1 条、iframe 1 个、报告 8 个 section、console 0 条 | `real_run.json`、`screenshots/02-report-preview.png`、`03-report-full.png` |
| S8 | 入库 | 完成 | 本任务文件同批提交；`check_board.py` 对 BCI-007 的三方一致项通过，全局 `TASK-COMMITTED` 仍受 BCI-004/006 既有未入库改动影响（非本任务） | `20261111-report-e2e/check.log`、Git 提交（BCI-007） |

## 4. 证据索引

- 主证据：`outputs/competitor-insights/BCI-007/20261111-report-e2e/`（`manifest.json`、`tests.log`、`check.log`、`real_run.json`、`preview.html`、3 张截图）
- DDL 证据：`outputs/competitor-insights/BCI-007/20261111-report-ddl/`（`manifest.json`、`apply.log`）
- 能力探针：`outputs/competitor-insights/BCI-007/20261108-pptx-probe/`
- 方案正文：`docs/report-output-design.md`（§0.4 已回写评估结论与落地偏差）
- 业务清单：`docs/report-output-business-inputs.md`

### 入库判定边界（共享文件 hunk）

`commit_paths` 不含 `app.py`、`home.html`、`competitor_insight/web/bci.js`（其他任务也在改）。本任务在这些文件中只占以下 hunk：

- `app.py`：`BCI_REPORT_API` 惰性工厂、`GET /api/bci/report/*`、`POST /api/bci/report/generate`、`_handle_bci_report_get/_post`、`_send_download`。
- `home.html`：`bci-report.css` 引用、tab ④ 去掉 `disabled` 与「下一步」、`data-bci-panel='report'` 面板、`bci-report.js` 引用、`bci.js?v=20261111c`。
- `competitor_insight/web/bci.js`：tab 分支 `initReport(root)` 与 `initReport()` 函数。

本批提交时 `home.html` 中属于 BCI-006 的 `bci-analysis.js?v=20261111b` 一行未纳入（仍留在工作区，由 BCI-006 自行提交）。

## 5. 已知边界（不是缺陷，但下游必须知道）

- 五款竞品：定量 30–41 人/车；深访 3–4 人/车。深访只出原话与人数，不出比例。
- **按车型实时统计**：本次五车范围可读档案 4 份（零跑B10 2、铂智3X 1、iCAR 1、海狮05 0、钛3 0），对应 16 场访谈；全库已生成档案 14 份，多数属其他车系，不进入本报告。页面分母随数据变化，不写死 10/63。
- 本品埃安RT：定量 0、深访提及 3 人、0 人是埃安车主；本品侧不出。
- 满意度明确分数仅 13/63。
- 8 个无来源维、无排序题、无未购车样本、无前车流水、无车型级别字段、2023/2024 定量未入库。
- PPT 本机无法渲染成图；模板自定义表格样式/图表配色不能完全继承；`.potx` 需先转 `.pptx`。

## 6. 遗留问题

| 编号 | 问题 | 影响 | 现状 | 解除条件 | 负责人 | 证据/关联 |
|---|---|---|---|---|---|---|
| BCI-007-L01 | 本品（埃安RT）定量样本 0、深访提及 3 人 | P05 本品侧、P09、P10 本品转化无法出 | 本期不出本品侧 | 业务补 ≥30 份本品定量样本 | 用户/业务 | `docs/report-output-design.md` §2 |
| BCI-007-L02 | 前车来源无数据（需中汽数据增换购流水 2026.1-8） | P02/P03 不出 | 已确认库内无表无字段 | 业务提供流水并入库 | 用户/业务 | B01-L04、业务清单 B06 |
| BCI-007-L03 | 无排序题、无首选率 | P06 不出；P04 品牌/产品/服务占比不出 | 已由 BCI-006 实测确认 | 业务补排序题 | 用户/业务 | BCI-006-L01 |
| BCI-007-L04 | 无未购车/流失样本 | 「竞品为什么赢」不出 | 已由 BCI-006 实测确认 | 业务补访未购车用户 | 用户/业务 | BCI-006-L03 |
| BCI-007-L05 | 满意度仅 13/63 有明确分 | P07 分数样本偏小 | 页面标注作答分母 | 补访 0–10 分题 | 业务 | BCI-004-L08 |
| BCI-007-L06 | 2023/2024 定量未入库 | 不做多年趋势 | 报告只出当前年度 | 完成入库并验证题项对齐 | 数据/TRAE | BCI-001-L04 |
| BCI-007-L07 | 对话改稿未做（原型为 3 条正则假实现） | 无法自然语言改稿 | 页面不出现输入框；结构化改稿方案已写 | 用户确认立项 + 20 份回归样本 + 数字白名单校验 | 用户 | `docs/report-output-design.md` §6 |
| BCI-007-L08 | 业务 PPT 模板未提供 | S6 无法开工 | 先做 HTML；PPT 二期 | 业务交付 `.pptx` 模板 | 用户/业务 | 业务清单 B04 |
| BCI-007-L09 | 五车范围可读档案仅 4 份（全库 14 份，多属其他车系） | 定性模块样本小 | 页面按车显示 `x/y 份档案有值`；不补数不插值 | 用户放开五车相关受访者的档案生成并完成 | 用户 | BCI-004、`preview.html` |
| BCI-007-L10 | 「学历」无来源 | P01 该行删除 | 定量分段无学历、档案 43 维无学历 | 业务补题或接受不展示 | 业务 | `docs/report-output-design.md` §2.2 |

## 7. 阶段流转记录

| 日期 | 阶段 | 依据 | 证据 | 变更人 |
|---|---|---|---|---|
| 2026-11-08 | CREATED | 用户要求先出方案与业务清单，不写业务代码 | `docs/report-output-design.md`、`20261108-pptx-probe/` | TRAE |
| 2026-11-11 | EXECUTING | 用户要求当天实现；评估结论「需改后可行」，6 项 P0 已按改进口径落地 | 本文件 §3 | TRAE |
| 2026-11-11 | TESTED | 单测 22/22、真实库 API 全链路、Playwright tab ④ 实测通过；本任务文件同批入库 | `20261111-report-e2e/`、`20261111-report-ddl/` | TRAE |

## 8. 第二轮：一车一报告 + 11 页 + 确定性改稿（2026-11-11）

| # | 验收项 | 判定方式 | 结果 |
|---|---|---|---|
| B1 | 一车一份 | 多选车型返回 400；同车型同指纹复用 | PASS：`multi_model_not_supported`；重跑 `reused` |
| B2 | 11 页齐全 | 生成报告 `content.pages` 长度 = 11 | PASS：P01–P11，附录不计入 |
| B3 | 不可用页 | P02/P03/P06/P09/P10 整页「暂未提供数据」+ 缺口原因，无表格、无「待补」 | PASS：截图 `P02/P06.png` |
| B4 | 页脚实时 n | 页脚按页实际块汇总源族；n 取档案数/问卷作答数/口碑去重条数 | PASS：P01 `n=2 + n=41`，P07 追加 `n=206` |
| B5 | 标题结论 | 序号-主题照原型；结论由模型按本车数据生成，数字必须在报告内，缺数据只写主题 | PASS：P05/P06/P09/P10 无结论；P01/P04/P07/P08/P11 结论含本车数字 |
| B6 | 确定性改稿 | 仅 `set_title/limit_items/append_refs`；数字子集校验；v1.1→v1.2 成链 | PASS：`20261111-report-v11/` E2E + UI |
| B7 | 结构化对比 | 按 block.id + 行键并排，不用逐字 diff | PASS：UI 对比面板 `P04.CHART`/`P11.BULLETS` |
| B8 | legacy 只读 | 旧五车报告 `legacy=true`，`/revise` 拒绝 | PASS：DDL 回填 5 条 legacy |
| B9 | P7 进攻方向接入 | P07.ATTACK 调 `AnalysisService.attack_point`（与 `GET /api/bci/analysis/attack-point` 同一实现），失败标缺不阻断报告 | PASS：零跑B10 v4.0 出 3 个方向（车内气味 18/195、路面滤震 12/79、实际续航 10/195），n=40；检索无结果时如实写「未做现状核验」 |

补充核对：`bci.report` 中 leapmotor-b10 的两条记录里，旧记录（`c882a856…`，标题「5 款车型竞品用户洞察报告」）已是 `legacy=true`，列表查询 `where r.legacy = false` 已过滤，业务侧只看到一条「1 款车型竞品用户洞察报告」。

证据：`outputs/competitor-insights/BCI-007/20261111-report-11p/`（11 页 HTML、逐页截图、verify.txt）、`20261111-report-footer/`、`20261111-report-v11/`（版本线截图）、`20261111-report-p7/`（P7 进攻方向页与截图）。

