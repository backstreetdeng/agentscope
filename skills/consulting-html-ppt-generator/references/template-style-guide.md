# Template Style Guide

Derived from `outputs/ppt/Template/PPT策划制作与咨询风工作流标准指南.html`.

## Visual DNA

- Background: `#f8fafc` with subtle radial blue/amber glow and thin horizontal texture.
- Primary color: cobalt blue `#1d4ed8`.
- Risk color: red `#c0392b`.
- Warning color: amber `#d97706`.
- Positive color: green `#15803d`.
- Fonts: Outfit + Noto Sans SC + JetBrains Mono.
- Slide radius: 12-18px cards; tables use 14px container.
- Use custom cursor: 32px blue circle, 52px hover state.

## Component Patterns

- `cover-slide`: bottom-aligned title, huge pale number at upper right, cover metadata row.
- `gold-rule-box`: blue/amber/red left-border callout; use for strategic principles or key conclusions.
- `scene-card`: repeated insight cards with dashed header, top colored border, compact core sentence.
- `quote-balloon`: risk/warning quote or shock statement; red left border and large quote glyph.
- `compare-layout`: two columns, bad vs good, red vs green, used for opportunity/risk or before/after.
- `timeline-layout`: horizontal process/action sequence.
- `table-container` + `sop-table`: dense business tables with clear headers.
- `wf-layout`: vertical workflow steps.
- `redlines-grid`: risk checklist or quality-control red lines.

## Story Rules

- Use conclusion titles, not labels. Bad: `区域产能调配建议`; good: `产能应向川渝与华南倾斜，高风险市场转为订单式供给`.
- Put the biggest decision early.
- For market reports, create a natural arc:
  1. Cover
  2. Executive decision summary
  3. Analysis boundary
  4. Market grading table
  5. Opportunity overview
  6. Opportunity detail pages
  7. Risk overview
  8. Risk detail pages
  9. Capacity allocation
  10. Go/no-go decision
  11. Evidence and assumptions
  12. Next action

## What Not To Do

- Do not output only a Markdown-to-slide conversion.
- Do not force every report into the same slide count.
- Do not use generic `用户圈层` pages for market strategy reports.
- Do not hide important tables; tables are acceptable in consulting decks when styled and bounded.
