---
name: consulting-html-ppt-generator
description: Generate premium consulting-style standalone HTML PPT decks from Chinese business reports, especially passenger vehicle market strategy, user insight, product configuration, policy, risk, capacity allocation, and go/no-go decision reports. Use when the user asks to create/generate/upgrade an HTML PPT, PPT版, 汇报版, 咨询风PPT, 麦肯锡/罗兰贝格风格 deck, or when an existing Markdown/text business report must become a polished slide presentation rather than copied text.
---

# Consulting HTML PPT Generator

Use this skill to convert a business report into a polished consulting-style HTML deck.

## Core Rule

Do not paste report paragraphs into a fixed deck. First convert the report into a storyline:

1. Identify report type: market strategy, user insight, product configuration, policy/risk, or mixed.
2. Extract chapters, tables, market/risk objects, strategic decisions, evidence, assumptions, and data gaps.
3. Choose slide types dynamically from the component system.
4. Generate a standalone HTML file with navigation, progress bar, custom cursor, and staggered animation.

## Required Style

Follow the template analyzed in `references/template-style-guide.md`.

Visual identity:

- Light paper background with subtle texture.
- McKinsey cobalt blue as primary accent.
- Red for warning/risk, amber for tension, green for positive/opportunity.
- Big conclusion titles, not neutral section labels.
- Dense but structured consulting pages: cards, tables, comparison columns, timelines, gold-rule callouts.
- Self-contained HTML with CSS and JS; no build step.

## Generation Script

Run:

```bash
python skills/consulting-html-ppt-generator/scripts/generate_deck.py \
  --input path/to/report.txt \
  --output path/to/report.html \
  --title "报告标题"
```

The script returns JSON with `success`, `slides_count`, `html_path`, `file_size`, and `engine`.

## Quality Gate

Before delivery, verify:

- HTML contains `updateUI()` and initializes it once.
- Keyboard navigation works with left/right arrows and space.
- Progress bar and `01/NN` page counter update.
- Custom cursor exists.
- Slides are generated from the report content, not a fixed 9-page template.
- Market strategy reports include opportunity, risk, capacity, go/no-go decision, and evidence pages when those sections exist.
