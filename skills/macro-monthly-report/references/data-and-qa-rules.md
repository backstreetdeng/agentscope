# Macro monthly data and QA rules

The ledger referenced below is created automatically by the agent during each run. It is not a workbook that the business user must prepare or upload.

## Source hierarchy

Prefer the original publisher for each series: 国家统计局, 中国人民银行, 海关总署, 财政部, 国家外汇管理局, 中国汽车工业协会, S&P Global/HCOB/Jibun Bank/ISM as applicable. Use Wind or reputable research only for series without a practical official feed, and keep the provider named in the source note.

Do not use a news article's rewritten number when the original release is available. If a secondary source is necessary, corroborate the latest value with a second credible source.

Wind/Mysteel provenance is not a required user credential. Execute the public
query plan and publisher-directory discovery before declaring a gap. Public
broker/futures reports require literal issuer identity and upstream attribution;
retain `source_grade=secondary` rather than relabelling them official. Distinct
mirrors of the same issuer count once. Historical observations retain their own
verifiable quotes; the latest secondary observation needs a second independent
issuer. Public PDF evidence is replayed from original bytes and page coordinates.
If actual scope, latest period or upstream identity cannot be proved, preserve
the precise unresolved indicator instead of vaguely requesting a Wind account.

## Release-calendar handling

- Monthly report month means the observation month, not the publication month.
- Quarterly series remain blank (`--`) in non-quarter monthly cells.
- Cumulative indicators must be labeled cumulative; monthly indicators must not be substituted for cumulative values.
- Forecast values must be visibly separated from actuals and appear only when requested.

## Known fragile slides and checks

### Overseas economy / PMI

- Verify United States, Japan, Eurozone, and China separately by series name.
- Confirm the same month and comparable manufacturing-PMI definition.
- Keep the expansion/contraction boundary at 50 across the full category range.
- Check the global composite, services, and manufacturing series are not confused in the headline.

### Automobile market

- Choose one explicit definition for the left chart. When the user asks for 中汽协汽车销量, use CAAM total automobile sales and its matching YoY; do not use passenger-car retail from CPCA.
- State whether figures are total sales, domestic sales, passenger vehicles, wholesale, retail, NEV, or exports.
- Check vehicles-to-万辆 conversion, cumulative versus monthly values, and primary/secondary axes.
- Future months must be blank and carry no data labels.

### Indicator overview and high frequency

- GDP is quarterly; use `--` in non-release months.
- Each high-frequency chart must use its own latest available date and must roll the start date with the end date.

## Pre-delivery audit table

For each delivered slide, record a pass/fail row for: data source, definition, date, unit, chart values, labels, narrative, source note, editable chart, external links, PowerPoint reopen, and rendered visual review. Resolve every failure before delivery.

## Executable typed-v2 contract

- The target-year seasonal curves keep fixed month/week categories; previous
  years are not overwritten with a synthetic month-end series. CPI-category,
  PMI-radar and loan-sector axes remain categories, not calendars.
- Series are updated by original native name, not `idx` or visible order. Keep
  original combination-chart plot membership, axes, date formatting, category
  formulas and display-unit conversions; roll date-axis min/max with dates.
- A source cell in 亿元 remains 亿元 when the existing axis displays 万亿元.
  Source units are not inferred from a chart legend or converted twice.
- Only independently evidenced observations enter prediction training.
  Template zero placeholders and template history are not forecast evidence.
  Minimum history is three monthly, four quarterly, eight weekly or ten daily
  points. LPR hold scenarios are separately labelled assumptions, not releases.
- Forecast method candidates are last level, three-period mean, damped trend
  and (with enough history) same-frequency seasonality. Select by walk-forward
  absolute error; retain candidate error, window, assumptions and uncertainty.
  Never fit a trend along different countries/categories.
- Missing target-month actual alone is not a blocker; insufficient verified
  historical baseline is. Keep these separate error codes.
- Slide 7 visible OLE snapshot is replaced by an editable table. Slide 32 uses
  the identical indicator objects. Preserve hidden think-cell metadata.
  GDP shows blank outside quarter-end months; no month repetition.
- Every target fact and caption distinguishes actual, forecast, missing and
  scenario. Rewrite old conclusions rather than globally renaming July.
- Wind/Mysteel series must retain their precise measurement definition; absent
  authorized feeds cannot be silently replaced with unrelated official numbers.
- Synthetic QA outputs may prove mechanics but cannot pass live source/business
  acceptance or be published as a monthly report.

## Independent acceptance gates

- A successful file open or a model's completion message is not business
  acceptance. Require independent source replay, native-chart/workbook and
  table validation, actual PowerPoint reopen/render, and measured layout on
  the same artifact SHA-256 before publishing. Record each gate separately.
- Office validation owns only its isolated presentation. If an existing user
  PowerPoint session cannot be safely isolated, wait for input instead of
  closing the user's presentations. Measurements must be newly produced for
  this artifact; never reuse a prior template's layout result.
- For the national CPI category table, replay the original HTML table with
  its hash, observation-month caption, exact category and exact monthly
  YoY/MoM column. Food is not food/tobacco/alcohol/restaurant spending, and a
  cumulative column or regional table is not a national single-month value.
- Check same-quarter GDP against the sum of its three demand contributions
  (percentage points; tolerance 0.2). Missing or inconsistent target/latest
  baseline components block acceptance; do not adjust published values to
  force an identity or compare different quarters.
- Forecast cumulative investment and fiscal amounts cannot decrease inside
  a year. A new-year reset needs an explicit model. These checks do not
  reject or rewrite the publisher's actual revisions or monthly net flows.
