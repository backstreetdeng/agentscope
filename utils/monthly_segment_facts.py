"""Local, period-labelled facts for the three category/level/model pages.

Flattened BI viewports omit empty cells. Never shift a partial model row into
the next model, or guess a missing year from a bare number. Only complete
comparison rows enter the model packet; calculations retain their operands.
"""
from __future__ import annotations

import re
from typing import Any

SEGMENT_PAGES = {9: "3", 10: "4", 11: "5"}
LEVEL = re.compile(r"^(?:A00|A0|A|B|C\+?|D)$")
INTEGER = re.compile(r"^\d[\d,]*$")
PERIOD = re.compile(r"^\d{4}-\d{2}$")


def segment_fact_draft(page: int, facts: dict[str, Any], month: str) -> dict[str, Any] | None:
    """A current-fact writing scaffold, never historical text or causal guesses.

    Select a within-level model contrast for sedan, cross-model opposite
    directions for SUV, and differing decline magnitudes for MPV. The model
    can refine the argument, but receives an already paired factual skeleton.
    """
    single = {row["level"]: row for row in facts["level_facts"] if row["scope"] == "single_month"}
    derived = facts.get("derived_facts", [])
    models = [row for row in facts["model_facts"] if row["scope"] == "single_month" and row.get("yoy_pct") is not None]
    if len(models) < 2:
        return None
    def volume(row):
        return f"{row['sales'] / 10000:.1f}万辆" if row["sales"] >= 10000 else f"{row['sales']}辆"
    def growth(row):
        return f"同比{'增长' if row['yoy_pct'] >= 0 else '下降'}{abs(row['yoy_pct']):.1f}%"
    def monthly(row):
        return f"环比{'增长' if row['mom_pct'] >= 0 else '下降'}{abs(row['mom_pct']):.1f}%"
    def quantity(number):
        return f"{abs(number) / 10000:.1f}万辆" if abs(number) >= 10000 else f"{abs(number)}辆"
    def claim(role, text, rows):
        return {"role": role, "claim": text, "fact_ids": [row["fact_id"] for row in rows],
                "evidence_ids": [], "certainty": "unverified"}
    month_label = f"{int(month[5:])}月"
    anomaly_type = "structural_divergence"
    if page == 9 and all(level in single for level in ("A0", "A", "B")):
        positive = [row for row in single.values() if row.get('yoy_pct', -1) > 0]
        core_relation = ("A0级是唯一同比正增长级别" if len(positive) == 1 and positive[0]['level'] == 'A0'
                         else "两级别同比一增一降" if single['A0']['yoy_pct'] * single['A']['yoy_pct'] < 0
                         else "两级别同比均增长" if min(single['A0']['yoy_pct'], single['A']['yoy_pct']) > 0
                         else "两级别同比均下降" if max(single['A0']['yoy_pct'], single['A']['yoy_pct']) < 0
                         else "两级别同比表现不同")
        core = claim("core", f"{month_label}轿车A0级{volume(single['A0'])}、{growth(single['A0'])}，A级{growth(single['A'])}，{core_relation}。", [single['A0'], single['A']])
        drag = next((row for row in derived if row.get('level') == 'A' and
                     row.get('largest_decline') and row.get('net_decline_share_pct') is not None), None)
        if drag:
            counter = "A0级的小幅增长尚难对冲" if single['A0']['yoy_pct'] > 0 else "主流级别收缩对总体规模影响更大"
            structure = claim("structure", f"A级同比净减{quantity(drag['sales_delta'])}，占轿车总净减{drag['net_decline_share_pct']:.1f}%，是主要拖累，{counter}。", [drag, single['A0']])
            anomaly_type = "contribution_concentration"
            title = f"2.3 轿车级别：A0级同比{'增长' if single['A0']['yoy_pct'] > 0 else '下降' if single['A0']['yoy_pct'] < 0 else '持平'}，A级收缩是主要拖累"
        else:
            state = "同比收缩" if single['B']['yoy_pct'] < 0 else "同比增长" if single['B']['yoy_pct'] > 0 else "同比持平"
            structure = claim("structure", f"B级单月份额{single['B']['share_pct']:.1f}%、{growth(single['B'])}，{volume(single['B'])}的销量规模与{state}共同影响级别结构。", [single['B']])
            title = "2.3 轿车级别：级别与代表车型同比表现分化"
        pairs = [(a, b) for a in models for b in models if a["model"] != b["model"] and
                 a.get("level") and a["level"] == b["level"] and a["yoy_pct"] * b["yoy_pct"] < 0]
        selected = max(pairs, key=lambda pair: pair[0]["sales"] + pair[1]["sales"]) if pairs else tuple(models[:2])
        relation = "同级代表车型一降一升，级别增长并非普遍改善" if pairs and single.get(selected[0]['level'], {}).get('yoy_pct', 0) > 0 else "同级代表车型一降一升" if pairs else "代表车型增速与所在级别不能简单等同"
    elif page == 10 and all(level in single for level in ("A0", "C+", "A", "B")):
        rhythm = "同比与环比方向相反" if single['C+']['yoy_pct'] * single['C+']['mom_pct'] < 0 else "同比与环比均增长" if min(single['C+']['yoy_pct'], single['C+']['mom_pct']) > 0 else "同比与环比均下降" if max(single['C+']['yoy_pct'], single['C+']['mom_pct']) < 0 else "同比与环比节奏不同"
        core = claim("core", f"{month_label}SUV的A0级{volume(single['A0'])}、{growth(single['A0'])}，C+级{growth(single['C+'])}、{monthly(single['C+'])}，{rhythm}。", [single['A0'], single['C+']])
        main_group = next((row for row in derived if row.get('levels') == ['A', 'B']), None)
        ends_group = next((row for row in derived if row.get('levels') == ['A0', 'C+']), None)
        if main_group and ends_group and main_group['sales_delta'] < 0 < ends_group['sales_delta'] and abs(main_group['sales_delta']) > ends_group['sales_delta']:
            structure = claim("structure", f"A/B合计占{main_group['group_share_pct']:.1f}%，同比净减{quantity(main_group['sales_delta'])}，A0与C+净增{quantity(ends_group['sales_delta'])}仍不足抵补主流级别收缩。", [main_group, ends_group])
            title = "2.3 SUV级别：两端增长难抵主流级别收缩，车型表现分化"
        else:
            state = "均增长" if min(single['A']['yoy_pct'], single['B']['yoy_pct']) > 0 else "均下降" if max(single['A']['yoy_pct'], single['B']['yoy_pct']) < 0 else "一增一降" if single['A']['yoy_pct'] * single['B']['yoy_pct'] < 0 else "表现不同"
            structure = claim("structure", f"A级{growth(single['A'])}、B级{growth(single['B'])}，单月份额分别为{single['A']['share_pct']:.1f}%与{single['B']['share_pct']:.1f}%，主流级别同比{state}。", [single['A'], single['B']])
            title = "2.3 SUV级别：级别与代表车型表现分化"
        positive = next((row for row in models if row["yoy_pct"] > 0), None)
        negative = next((row for row in models if row["yoy_pct"] < 0), None)
        selected = (positive, negative) if positive and negative else tuple(models[:2])
        relation = "代表车型一升一降，与其所在级别方向相同" if positive and negative and all(single.get(row['level'], {}).get('yoy_pct', 0) * row['yoy_pct'] > 0 for row in selected) else "代表车型一升一降，不能以单一车型概括市场" if positive and negative else "代表车型增速与所在级别不能简单等同"
    elif page == 11 and all(level in single for level in ("A0", "A", "B")):
        opposite = single['A']['yoy_pct'] * single['A0']['yoy_pct'] < 0
        deltas = {row['level']: row['sales_delta'] for row in derived if row.get('level')}
        insufficient = (deltas.get('A', 0) > 0 and deltas.get('A0', 0) < 0 and deltas.get('B', 0) < 0 and deltas['A'] < -(deltas['A0'] + deltas['B']))
        core = claim("core", f"{month_label}MPV的A级{growth(single['A'])}，A0级{growth(single['A0'])}，两者同比{'方向相反' if opposite else '均增长' if min(single['A']['yoy_pct'], single['A0']['yoy_pct']) > 0 else '均下降' if max(single['A']['yoy_pct'], single['A0']['yoy_pct']) < 0 else '表现不同'}，{'A级增长仍难抵补其他级别收缩' if insufficient else '细分市场规模和增长节奏需区分'}。", [single['A'], single['A0'], single['B'], *[row for row in derived if row.get('level') in ('A','A0','B')]])
        b = single['B']
        shift = next((row for row in derived if row.get('level') == 'B' and row.get('share_change_pp') is not None), None)
        share_text = (f"份额较上月{'提高' if shift['share_change_pp'] >= 0 else '下降'}{abs(shift['share_change_pp']):.1f}个百分点至{b['share_pct']:.1f}%" if shift else f"单月份额{b['share_pct']:.1f}%")
        structure = claim("structure", f"B级{monthly(b)}，{share_text}，{growth(b)}，主体市场{'仍承压' if b['yoy_pct'] < 0 else '同比增长' if b['yoy_pct'] > 0 else '同比持平'}。", [b, *([shift] if shift else [])])
        selected = tuple(models[:2])
        relation = "代表车型同比均下降，B级内部承压程度不同" if all(row['yoy_pct'] < 0 for row in selected) else "代表车型同比均增长" if all(row['yoy_pct'] > 0 for row in selected) else "代表车型同比一增一降" if selected[0]['yoy_pct'] * selected[1]['yoy_pct'] < 0 else "代表车型同比表现不同"
        title = f"2.3 MPV级别：{'A级与A0级方向相反' if opposite else 'A级与A0级同比均增长' if min(single['A']['yoy_pct'], single['A0']['yoy_pct']) > 0 else 'A级与A0级同比均下降' if max(single['A']['yoy_pct'], single['A0']['yoy_pct']) < 0 else 'A级与A0级表现不同'}，B级{'同比收缩' if b['yoy_pct'] < 0 else '同比增长' if b['yoy_pct'] > 0 else '同比持平'}"
    else:
        return None
    model_text = "，".join(f"{row['model']} {volume(row)}、{growth(row)}" for row in selected)
    return {"slide": page, "headline": title, "headline_evidence_ids": [],
            "anomaly": {"type": anomaly_type, "priority": 7,
                        "fact_ids": [row['fact_id'] for row in [*selected, *derived]]},
            "body_claims": [core, structure, claim("models", model_text + "，" + relation + "。", selected)]}


def _previous(month: str) -> str:
    year, number = map(int, month.split("-"))
    return f"{year - 1}-12" if number == 1 else f"{year}-{number - 1:02d}"


def _views(text: str):
    for part in text.split("---视图分段---"):
        yield [line.strip() for line in part.splitlines() if line.strip()]


def _growth(current: int, baseline: int) -> float | None:
    return round((current / baseline - 1) * 100, 1) if baseline else None


def _level_rows(text: str, cumulative: bool) -> dict[str, dict[str, int]]:
    rows: dict[str, dict[str, int]] = {}
    for lines in _views(text):
        label = "年" if cumulative else "日期组合 (月)"
        if label not in lines:
            continue
        start = lines.index(label) + 1
        end = next((i for i in range(start, len(lines)) if
                    (re.fullmatch(r"\d{4}", lines[i]) if cumulative else PERIOD.fullmatch(lines[i]))), len(lines))
        labels = lines[start:end]
        levels = []
        for value in labels:
            if not LEVEL.fullmatch(value) or value in levels:
                break
            levels.append(value)
        for i in range(end, len(lines)):
            key = lines[i]
            if not (re.fullmatch(r"\d{4}", key) if cumulative else PERIOD.fullmatch(key)):
                continue
            values = []
            for value in lines[i + 1:]:
                if not INTEGER.fullmatch(value):
                    break
                # The following year is another row, not a vehicle count.
                if cumulative and value in {str(int(key) - 1), str(int(key) + 1)}:
                    break
                values.append(int(value.replace(",", "")))
            if len(values) == len(levels):
                rows[key] = dict(zip(levels, values))
            elif len(values) == len(levels) - 1 and levels[-1:] == ["C+"]:
                # Omitted final C+ cell is never materialised as zero.
                rows[key] = dict(zip(levels[:-1], values))
    return rows


def _model_rows(text: str, month: str, cumulative: bool) -> list[dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for lines in _views(text):
        if "车型" not in lines:
            continue
        start = lines.index("车型") + 1
        periods = []
        while start < len(lines):
            value = lines[start]
            if value.startswith("车型级别"):
                start += 1
                continue
            if (re.fullmatch(r"\d{4}", value) if cumulative else PERIOD.fullmatch(value)):
                periods.append(value)
                start += 1
                continue
            break
        expected = [str(int(month[:4]) - 1), month[:4]] if cumulative else [
            _previous(f"{int(month[:4]) - 1}-{month[5:]}"),
            f"{int(month[:4]) - 1}-{month[5:]}",
            _previous(month), month,
        ]
        # Header positions, not a heuristic about new models, determine scope.
        if periods[:len(expected)] != expected:
            continue
        i = start
        while i < len(lines):
            name = lines[i]
            if name.startswith(("加载", "已追加")):
                break
            if INTEGER.fullmatch(name) or LEVEL.fullmatch(name) or "%" in name:
                i += 1
                continue
            i += 1
            level = lines[i] if i < len(lines) and LEVEL.fullmatch(lines[i]) else ""
            if level:
                i += 1
            values = []
            while i < len(lines) and INTEGER.fullmatch(lines[i]):
                values.append(int(lines[i].replace(",", "")))
                i += 1
            while i < len(lines) and ("%" in lines[i] or lines[i] == "-"):
                i += 1
            if len(values) != len(expected):
                continue
            record = {"model": name, "level": level, "period": month,
                      "scope": "year_to_date" if cumulative else "single_month",
                      "sales": values[-1], "comparison_sales": values[-2] if cumulative else values[1],
                      "yoy_pct": _growth(values[-1], values[-2] if cumulative else values[1])}
            if not cumulative:
                record.update(previous_month_sales=values[2], mom_pct=_growth(values[-1], values[2]))
            result.setdefault(name, record)
    return list(result.values())


def segment_page_facts(page: int, cards: dict[str, dict[str, Any]], month: str) -> dict[str, Any]:
    group = SEGMENT_PAGES[page]
    period_codes = [f"P2-{group}.1", f"P2-{group}.2"]
    model_codes = [f"P2-{group}.3A", f"P2-{group}.3B"]
    single = _level_rows(str(cards.get(period_codes[0], {}).get("text", "")), False)
    cumulative = _level_rows(str(cards.get(period_codes[1], {}).get("text", "")), True)
    prior = f"{int(month[:4]) - 1}-{month[5:]}"
    total = sum(single.get(month, {}).values())
    ytd_total = sum(cumulative.get(month[:4], {}).values())
    levels = []
    for level, sales in single.get(month, {}).items():
        row = {"fact_id": f"{period_codes[0]}:{level}:{month}", "level": level,
               "scope": "single_month", "sales": sales,
               "share_pct": round(sales / total * 100, 1) if total else None,
               "yoy_pct": _growth(sales, single.get(prior, {}).get(level, 0)),
               "comparison_sales": single.get(prior, {}).get(level), "total_sales": total}
        previous_month = _previous(month)
        row["previous_month_sales"] = single.get(previous_month, {}).get(level)
        row["mom_pct"] = _growth(sales, row["previous_month_sales"] or 0)
        previous_prior = _previous(prior)
        row["previous_month_yoy_pct"] = (_growth(
            row["previous_month_sales"], single.get(previous_prior, {}).get(level, 0))
            if row["previous_month_sales"] is not None else None)
        for field, comparison_period in (("previous_month_share_pct", previous_month), ("prior_year_share_pct", prior)):
            comparison = single.get(comparison_period, {})
            comparison_total = sum(comparison.values())
            row[field] = (round(comparison[level] / comparison_total * 100, 1)
                          if comparison_total and level in comparison and comparison.keys() == single[month].keys() else None)
        levels.append(row)
    for level, sales in cumulative.get(month[:4], {}).items():
        levels.append({"fact_id": f"{period_codes[1]}:{level}:{month}", "level": level,
                       "scope": "year_to_date", "sales": sales, "total_sales": ytd_total,
                       "share_pct": round(sales / ytd_total * 100, 1) if ytd_total else None,
                       "comparison_sales": cumulative.get(str(int(month[:4]) - 1), {}).get(level),
                       "yoy_pct": _growth(sales, cumulative.get(str(int(month[:4]) - 1), {}).get(level, 0))})
    ytd_models = _model_rows(str(cards.get(model_codes[1], {}).get("text", "")), month, True)
    model_levels = {row["model"]: row["level"] for row in ytd_models}
    models = _model_rows(str(cards.get(model_codes[0], {}).get("text", "")), month, False)
    overall_models = {row["model"]: row for row in _model_rows(
        str(cards.get("P2-14.1", {}).get("text", "")), month, False)}
    # A small set of leaders and contrasting directions, not all DOM rows.
    selected = sorted(models, key=lambda row: -row["sales"])[:4]
    for row in selected:
        row["level"] = row["level"] or model_levels.get(row["model"], "")
        overall = overall_models.get(row["model"], {})
        if not row["level"] and overall.get("sales") == row["sales"]:
            row["level"] = overall.get("level", "")
            row["level_source"] = "P2-14.1"
        row["fact_id"] = f"{model_codes[0]}:{row['model']}:{month}"
    for row in ytd_models:
        if row["model"] in {item["model"] for item in selected}:
            row["fact_id"] = f"{model_codes[1]}:{row['model']}:{month}"
            selected.append(row)
    return {"level_facts": levels, "model_facts": selected,
            "derived_facts": _derived_segment_facts(page, levels, month),
            "coverage_requirement": {"minimum_models": 2, "minimum_model_metrics": 2,
                                     "required_layers": ["级别核心分化", "代表车型对照"],
                                     "body_display_width": "125-150", "maximum_lines": 3,
                                     "missing_cell_rule": "不使用无法定位月份的车型数值，不补同比，不用旧报告事实"}}


def _derived_segment_facts(page: int, levels: list[dict[str, Any]], month: str) -> list[dict[str, Any]]:
    """Compute relations locally, keeping raw operands and the precise scope.

    Net category contribution is allowed only when the complete comparison
    universe is present. A missing MPV C+ cell must not be silently zeroed.
    Group shares use raw sales, never the sum of rounded share percentages.
    """
    single = {row['level']: row for row in levels if row['scope'] == 'single_month'}
    expected = {9: {'A00', 'A0', 'A', 'B', 'C+'}, 10: {'A0', 'A', 'B', 'C+'},
                11: {'A0', 'A', 'B', 'C+'}}[page]
    complete = single.keys() == expected and all(row.get('comparison_sales') is not None for row in single.values())
    total_delta = sum(row['sales'] - row['comparison_sales'] for row in single.values()) if complete else None
    result = []
    group = SEGMENT_PAGES[page]
    deltas = {level: row['sales'] - row['comparison_sales'] for level, row in single.items()
              if row.get('comparison_sales') is not None}
    for level, row in single.items():
        if level in deltas:
            record = {'fact_id': f'P2-{group}.1:derived:{level}:{month}', 'scope': 'single_month',
                      'level': level, 'sales_delta': deltas[level],
                      'sales_comparison_scope': 'prior_year_same_month',
                      'operands': {'current_sales': row['sales'], 'comparison_sales': row['comparison_sales']},
                      'method': 'current_sales-comparison_sales', 'source_fact_ids': [row['fact_id']]}
            if complete:
                record['operands']['total_delta'] = total_delta
                record['source_fact_ids'] = [item['fact_id'] for item in single.values()]
                record['largest_decline'] = deltas[level] < 0 and deltas[level] == min(deltas.values())
                if total_delta < 0 and deltas[level] < 0:
                    record['net_decline_share_pct'] = round(deltas[level] / total_delta * 100, 1)
                    record['method'] += ';negative_delta/total_negative_delta*100'
            previous = row.get('previous_month_share_pct')
            if previous is not None and row.get('share_pct') is not None:
                record['share_change_pp'] = round(row['share_pct'] - previous, 1)
                record['share_comparison_scope'] = 'previous_month'
                record['operands'].update(current_share=row['share_pct'], previous_share=previous)
                record['method'] += ';current_share-previous_share'
            result.append(record)
    if page == 10 and complete:
        total_sales = sum(row['sales'] for row in single.values())
        for labels in (['A', 'B'], ['A0', 'C+']):
            result.append({'fact_id': f"P2-{group}.1:derived:{'+'.join(labels)}:{month}",
                           'scope': 'single_month', 'levels': labels,
                           'sales_comparison_scope': 'prior_year_same_month',
                           'group_share_pct': round(sum(single[label]['sales'] for label in labels) / total_sales * 100, 1),
                           'sales_delta': sum(deltas[label] for label in labels),
                           'operands': {'current_sales': {label: single[label]['sales'] for label in labels},
                                        'comparison_sales': {label: single[label]['comparison_sales'] for label in labels},
                                        'total_sales': total_sales},
                           'method': 'sum(current_sales)/total_sales*100;sum(current_sales-comparison_sales)',
                           'source_fact_ids': [row['fact_id'] for row in single.values()]})
    return result
