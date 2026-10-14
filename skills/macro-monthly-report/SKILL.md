---
name: macro-monthly-report
description: "Study and update 中汽数据宏观经济月报 from historical PowerPoint reports: preserve historical series and editable layouts, collect new-period observations, and derive evidence-backed thematic headlines. Distinguish retrospective monthly analysis plus next-month outlook from an explicit forecast task; check the web adapter's supported modes before execution."
---

# 宏观经济月报 Monthly Update

Use the retained presentation as the visual and structural baseline. Never overwrite it.

## 先识别业务任务（2026-10-13 三份样例学习）

先读 [references/historical-update-workflow.md](references/historical-update-workflow.md)
处理“参考优秀月报学习”“基于历史数据增加新月份”“生成某月经济分析报告”及主题句提炼。
三份5—7月样例已随包保存在 `assets/history/`；文件哈希与页数见
`references/history-manifest.json`。用 `scripts/study_reference_decks.py` 显式传入
这些文件，生成完整文本、图表缓存、公式和表格清单；原文件只读。

用户要求回顾某月经济运行时，业务目标是该月实际分析与**下一个月**前瞻。
例如8月报告：正文8月、发行月通常9月、预测页9月；报告月份不是整套预测终点。
截至日独立保存；历史复盘不使用截至日之后的政策或数据修订解释当时判断。
用户明确要求预测某月时才采用下文现有 forecast 执行流程。只给月份且语义不明时，
依据是否为历史复盘、实际数据发布情况和上下文判定，必要时询问，不能一律预测。

**执行能力状态：已实现 `mode=historical_update`，使用独立逐轮验收记录确定是否允许下载。**
网页只需选择报告月份，不展示报告方式、预测版或公开草稿选项。
统一采用当月分析与下月前瞻。无法更新的图表保留模板历史与原统计日期，
明确标注“暂无可核验数据”，不得将模板历史冒充本期实际。
有未更新页时为“部分完成”，可下载已验收PPT；所有页均有本期数据支持时才为“完成”。
下次打开同一任务可继续执行，仅补采缺项页所需的未核验指标；保留已采集原文凭据、
成功数据和历史资产，不重新采集已成功项。后台内部使用 historical_retained 兼容已有记录，
但不将这些内部模式或授权标志作为用户选项。
历史模式执行 `macro_history.py` → `macro_sources.collect_sources` →
`build_macro_historical.py` → `validate_macro_historical.py`，使用36图新版参考；
历史观测及跨月差异自动保存，新增实际仅来自原文复核。
`macro_historical_derivations.py` 仅从央行明确累计新增贷款流量推算月度增量，
必须同时保留两个原文、单位换算、约数及舍入误差；不能用余额差代替增量。
也不能用公开数据草稿替代用户要求的历史正式报告。下文“默认forecast”和固定33页/37图
说明只描述旧版适配器的现有行为，不覆盖本节的业务任务判断。
完整本期交付与历史延续版分别验收；不能用历史延续版的通过结果宣称全量本期数据完整。
不得直接覆盖 `assets/reference.pptx`：7月新样例为33页36图，与当前33页37图的
固定对象契约不同。先按指标含义重新映射、验证，再切换底稿。

## Business invocation

Business users may run this skill directly. The only required input is the target report month. Scope, cutoff date, requested slides, forecast scenario, and confidence level are optional.

No Wind, Mysteel or other commercial account is a prerequisite for business
invocation. Supplier names in the reference identify provenance, not interfaces
the user must purchase. Read `references/source-queries.json` and
`references/public-source-policy.json`; the executor must actually use the public
retrieval plan. Start from publisher release directories and date-specific web
discovery. Where an original public feed is impractical, a named public research
report with literal upstream attribution is admissible under the secondary-source
rules. Corroborate its latest value with a different original report issuer;
copies of one report are not independent. Keep every real period, definition,
unit, publication date and original page/PDF receipt. Never bypass login or
quietly substitute similar series. Report specific evidence gaps only after
these public paths have actually been attempted.

The existing web adapter defaults to **forecast mode** when passed only a month.
This is an adapter limitation, not the business interpretation for a retrospective
monthly analysis; use the task distinction above before selecting that adapter.
For an explicitly requested forecast, the target month is the forecast horizon,
not a requirement that all target-month actual observations already exist. Use
the latest authoritative actuals available at the execution cutoff as the
historical baseline and forecast the unreleased target-period values. Clearly
distinguish actual, forecast, scenario, and unreleased values.

The web adapter supports full-deck forecast and historical_update modes. Historical
mode updates this month's actuals and separately forecasts next month. Partial-slide
scope remains unsupported. Do not silently change task modes, require a user-built
ledger, or turn an incomplete formal report into a public draft.

The workbench also offers an explicit **公开数据草稿** choice for basic usability
when exact public coverage is incomplete. It is not a fallback or formal report:
require `delivery_mode=public_draft` and `public_draft_confirmed=true`, preserve
the same run and source receipts, and show the draft boundary in the report and
download UI. `build_macro_draft.py` uses independently replayed actuals only,
never forecasts, copies archived numeric history or fills absent values. It
recreates compact editable chart workbooks, clears old labels and dated claims,
rebuilds notes, and visibly marks missing data. `validate_macro_draft.py` checks
source replay, chart/workbook cells, text, tables and gaps independently; it
cannot grant formal acceptance. Structure and actual PowerPoint/render/layout
gates still apply. Only a `draft_ready` run passing these gates may use its
dedicated `/api/macro-report/draft/<run_id>` download. Formal checks and formal
downloads remain unchanged. A failed full report cannot silently become a draft;
start a separately chosen draft task, never mix their checkpoints.

For this explicit basic draft, collect deterministic public actuals only: read
up to three recent original-release pages per reviewed indicator initially, preserve
exact proof checks, and do not run model locators or prediction-history
supplements. Failed or insufficient candidates trigger up to three different
date/definition-specific recovery queries, each reading at most three new
approved URLs for unresolved requests only. Save discovery and processing
checkpoints under `working/macro-sources/recovery/`; replay successful receipts
on resume. Login redirects, HTTP failures and parser gaps are separate from
unreleased statistics. Keep exclusive reviewed vintage restrictions and all
source/definition/unit/date/corroboration gates. Report unresolved paths rather
than asserting that statistics do not exist.
Failure-driven discovery also applies to formal collection. Formal prediction
methods and acceptance rules remain unchanged.

For another task targeting the same report month, automatically replay the
successful indicators from prior local Skill runs before collection. Match the
statistical request, revalidate original receipts with current code and cutoff,
and apply current freshness, history and corroboration requirements. Copy only
verified actual evidence into the new isolated run; do not inherit old PPTs,
forecasts, task completion or delivery acceptance. Collect unresolved indicators
only, including previously successful ones that now require newer actuals.
Retain Customs' current bulletin-vintage discovery. Persist `source_reuse` and
per-indicator origin run IDs, and show reused/pending counts in real progress.
Different report months and later-cutoff snapshots are not reusable substitutes.

When the user prioritizes basic usability over analysis quality, concentrate on
the executable web-to-PPT path. Use the existing deterministic fact-based
narrative; do not add model headline rewrites, causal research or polish gates
to that critical path. Data truth, actual/forecast labels, native editability
and a usable downloadable artifact still matter. Lower writing quality does
not authorize filling missing data or changing statistical definitions. If a
usable first delivery requires omitting data or making a visibly incomplete
draft, obtain that scope choice instead of quietly relabelling it complete.

## Build the working ledger internally

Before editing, the agent must inventory every data-bearing slide and create an internal working ledger with: slide, indicator, statistical definition, unit, frequency, source, latest officially available period, old value, new value, and affected title/body/chart/table/annotation. Use it as the single source of truth for the deck.

This ledger is an execution and audit artifact created by the agent, not a prerequisite supplied by the business user. Retain it with the task evidence and expose it after completion only when useful for review.

For full-month requests, inspect every slide; do not infer freshness from an updated axis or filename. A future partial-slide adapter must update and export only the requested slides unless the user asks for the full report; the current adapter rejects partial requests explicitly.

Read [references/data-and-qa-rules.md](references/data-and-qa-rules.md) whenever the task changes data, charts, narrative, or produces a deliverable PPTX.

## Update workflow

### Executable backend (typed-v2)

The web workbench creates a durable `macro-...` run immediately. It executes the
following package assets inside that run; neither the Agent nor the LLM may
substitute a Markdown-to-PPT export or the retained template-only executor:

1. `scripts/inspect_macro_template.py working/template-contract.json`: inspect
   all 33 slides, 37 chart parts, text including groups, and source requests.
   `scripts/macro_contract.py` is the reviewed frequency/category/unit registry.
   Template/registry drift fails explicitly.
2. `scripts/macro_sources.py::collect_sources`: use
   `scripts/macro_official_discovery.py` to locate current and historical official
   releases, execute the retained source query plan, and search original publishers
   and reviewed public research,
   fetch and retain original page text, publication date, URL, SHA256 and exact
   observation proof. A selected provider may locate values in PUBLIC source
   text; it does not receive the internal template or raw internal data.
   Public PDF receipts retain original bytes, hashes and per-page quotes. Record
   original statistical producer separately from public report publisher.
   Search snippets, fabricated quotations, country/scope swaps and future
   publications cannot enter the actual-data package.
   Use the package-local reviewed table readers for NBS industrial production,
   retail/PPI, aggregate/core/food CPI, national real-estate investment/sales
   cumulative growth, PBC AFRE flows and PBC M1/M2/AFRE-stock growth. Preserve the source
   HTML and physical cell coordinates; do not ask an LLM to reconstruct these
   tables. PBC nonstandard financing is the same-period sum of entrusted loans,
   trust loans and undiscounted bankers' acceptances; direct financing is
   corporate bonds plus domestic equity financing by nonfinancial enterprises,
   excluding government bonds. Mark these as derived, keep every input cell and
   formula version, and independently recompute them during acceptance. Other
   missing derived indicators need their own reviewed input/formula proof; these
   two sums are not permission to invent GDP, balance differences or forecasts.
   PBC financial-report prose uses exact title/month/section and literal growth
   sentences, not balance values or cumulative credit amounts. M1 requires the
   source's revised-definition note (personal demand deposits and nonbank payment
   institution customer reserves); never merge an unproved older M1 definition.
   `macro_nbs_investment_profit.py` reads cumulative fixed-asset investment
   amounts from the national-economy main-indicators appendix, investment/private/
   manufacturing growth from their exact original rows, and automobile-industry
   cumulative profit growth from the profit (not revenue) column. A growth table
   alone does not prove the private-investment amount or narrower infrastructure.
   `macro_mof_fiscal.py` binds the national general-public-budget income/expenditure
   section and its cumulative amount/growth sentences; exclude government funds,
   regional amounts and URL creation dates. Keep raw amounts in 亿元; display
   scaling belongs to the separately verified chart transformation.
   `macro_nbs_gdp.py` distinguishes current-quarter constant-price growth,
   cumulative growth and directly published demand-pull percentage points.
   Discover the annual national statistical bulletin for an explicitly dated Q4;
   do not multiply contribution shares into invented pull points or substitute
   an unproved GDP deflator. Independently check demand-pull sums within the
   reviewed publisher-rounding tolerance without adjusting any actual value.
   `macro_pbc_lpr.py` binds the original LPR announcement's actual publication
   day and 1-year/5-year-above tenors; do not assume every release is on the 20th
   or replace LPR with SHIBOR, another policy rate or a made-up monthly value.
   `macro_nbs_grouped_prose.py` binds manufacturing PMI group members and
   new-home city tiers to their literal current-month sentences. It distinguishes
   a transition's current change from its prior rate. An explicit "转为持平"
   means zero only after that registered reader independently replays the
   original period, tier and sentence. PMI's percent notation remains an index
   level, not a fraction. Generic physical-cell parsing of merged PMI headers
   must not assign the aggregate index to another component.
   `macro_nbs_pmi_tables.py` expands the original two-level manufacturing PMI
   header and binds all twelve component columns by name, rather than their
   physical position in a shortened header row. Prose and tables must agree;
   a conflicting value is not averaged into a usable observation.
   `macro_customs_discovery.py` reads the Customs original USD directories.
   Export/import monthly YoY comes from the preliminary trade-mode rows;
   monthly balance comes from one latest, dated Monthly Bulletin containing
   the required history. `macro_customs_trade.py` replays the original cells.
   The USD-million balance is divided by 100 for 亿美元 with a private formula
   proof, not recomputed from rounded exports/imports. The selected per-request
   URLs constrain collection, cached queries and historical supplementation;
   older balance vintages remain audit receipts, never business substitutes.
   Real-estate readers preserve investment/sales, area/amount and cumulative/monthly
   distinctions. Unsupported housing-stock, infrastructure and loan-increment
   definitions need separately reviewed readers; similar labels are not substitutes.
3. `scripts/build_macro_report.py YYYY-MM working/data-package.json
   outputs/report.pptx working/macro-ledger.json`: replay evidence, normalize by
   series meaning, forecast only on independently verified history, update native
   chart caches AND embedded workbooks, update date bounds and value autoscaling,
   rebuild editable overview and forecast tables, and rewrite narrative from
   final facts. Quarterly/weekly/daily, radar snapshots, category metrics and
   seasonal-year charts use different algorithms. Original masters remain.
4. `scripts/validate_macro_report.py outputs/report.pptx working/macro-ledger.json`:
   independently replay the original evidence and data transformation; compare
   caches with referenced workbook cells, final values with ledger, both tables
   with shared facts, and all updated text with the ledger.
   `scripts/macro_constraints.py` separately checks GDP demand contributions
   against cumulative GDP growth, and rejects decreasing or unmodelled cross-year
   cumulative-amount forecasts. Never numerically balance or alter publisher actuals.
5. Run `macro_business`, `pptx_structure`, `powerpoint_render`, `macro_layout`, plus full runtime
   plan/artifact validation. Only then publish the same `run_id` artifact.
   `scripts/validate_macro_layout.py` owns an isolated Office session, saves and
   reopens only a diagnostic copy, renders all 33 slides, and measures the final
   artifact's actual text bounds/table cells. A user's open PowerPoint is untouched.

The old `generate_forecast_baseline.py` is retained for diagnostic reproduction
only, never a formal fallback. A file that opens is not evidence of current data.
Incomplete source/history leaves a recoverable blocked run with precise issues;
it does not destroy validated sources or quietly fill with template values.
Package hashes and checkpoint fingerprints prevent mixed-version resumes.

The legacy executable backend described in this section supports full-deck forecast
mode; historical_update uses its own 36-chart profile above. Partial-slide execution
is rejected before collection.

1. Read `artifact-template.json`, resolve paths relative to this directory, and load the presentation skill.
2. Clone/import the retained reference. Preserve masters, layouts, logo, typography, colors, spacing, page chrome, and chart styling.
3. Inspect the requested scope and automatically build the internal working ledger from the template.
4. Research the newest authoritative observations available at the execution cutoff. Record exact periods, sources, definitions, and units in the ledger.
5. In forecast mode, choose a defensible method for each series, document assumptions, backtest when sufficient history exists, and create a separate forecast segment through the requested month. Missing target-month actuals are forecast outputs, not completeness failures.
6. Update the embedded chart/table data first. Then update axes, labels, annotations, titles, body conclusions, source notes, cover month, issue month, and filename from the final values.
7. Keep every chart and table native and editable. Embed chart workbooks; do not use linked workbooks, screenshots, flattened plots, or local-file dependencies.
8. Run the data, package, PowerPoint-open, and visual gates below. Deliver only after all gates pass.

## Statistical-definition rules

- Never mix institutions or definitions inside one series or comparison without an explicit label. In particular, distinguish 中汽协汽车总销量、汽车国内销量、乘联分会乘用车零售、厂商批发和出口.
- For country/region comparisons, map each value by series name—not visual order—and verify the final endpoint label against the narrative sentence.
- Treat reference series such as PMI expansion/contraction boundary as constants. The PMI boundary is `50` for every period and must never be included in generic “append latest value” logic.
- GDP is quarterly. Monthly overview cells outside release months show `--`; never repeat a quarterly value as a monthly observation.
- In forecast mode, an unreleased target-period observation must be forecast and labelled `预测`; the last official observation must retain its actual period or `更新至` date. Never present a forecast as an actual.
- In historical-update mode, if an indicator has not been released, retain the latest official observation and label its actual period; do not silently forecast it.
- High-frequency series may have different cutoff dates. Show the latest date, value, unit, and source for each series.
- Preserve units through all transformations. If source data are vehicles but the chart unit is 万辆, convert once and verify axis, labels, body text, and source table use the same unit.

## Chart update rules

- Update series by name and meaning, never only by series index. Explicitly identify series that must not change.
- Extend monthly charts through the requested month and shift the rolling start by the same number of months, preserving the window length.
- Update the series formula/range, category range, endpoint callout, axis bounds, tick labels, legend, and prose together.
- Actual series must keep unreleased future months as true blanks. Forecast series may populate those months, but must use a distinct series name, styling, legend, and source/assumption note; never insert future zeroes or disguise forecasts as actuals.
- Recalculate YoY, MoM, percentage-point changes, cumulative values, rankings, arrows, and direction language from the final series.
- For combination charts, verify primary/secondary axes, display units, number formats, and data-label positions after writing data.

## Required consistency gate

For each updated slide, compare the final rendered slide against the ledger:

- latest period and value;
- series/region mapping;
- unit and statistical definition;
- headline and body statement;
- chart endpoint/callout and table cell;
- source note.

Any disagreement is a failure. Rewrite narrative from the final chart data rather than carrying forward prior-month prose.

## Required deliverable gates

1. Package integrity: no missing internal relationships, corrupt chart parts, or external workbook/file links.
2. Editability: charts remain native PowerPoint charts with embedded data; tables and text remain editable.
3. PowerPoint validation: close the generated file, reopen it in Microsoft PowerPoint, confirm no repair or linked-file warning, and save/reopen once more when chart data were rewritten.
4. Visual validation: render every delivered slide and inspect at readable resolution for clipping, overlap, wrong labels, `#N/A`, stale months, distorted axes, template drift, and unreadable source notes.
5. Content validation: spot-check every latest endpoint and all headline numbers against the ledger; for full reports, scan all slides for prior-month text.

If PowerPoint validation cannot be completed, do not claim the file is validated. Report the limitation and keep working on a safer output path.

## Delivery

Name the new file for the requested report month and supported scope. Return a new copy and mention the data cutoff and any indicators whose official period lags. Unsupported historical-only or subset requests must not be reported as completed.
