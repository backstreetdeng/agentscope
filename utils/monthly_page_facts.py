"""Typed, local business facts for non-segment monthly-report pages.

Read complete quantity rows from dated, left-hand BI viewports. Percentages
are calculated from those quantities, never assigned by a flattened percent
array. Missing cells, conflicting observations and unproved year/denominator
bindings remain warnings rather than becoming invented zeroes.
"""
from __future__ import annotations

import re
from typing import Any

_MONTH = re.compile(r"^\d{4}-(?:0[1-9]|1[0-2])$")
_YEAR = re.compile(r"^\d{4}$")
_BARE_MONTH = re.compile(r"^(?:0[1-9]|1[0-2])$")
_INTEGER = re.compile(r"^\d[\d,]*$")
_PERCENT = re.compile(r"^(-?\d+(?:\.\d+)?)%$")
_QUANTITY_HEADERS = {"数量", "销量", "库存量"}
_REGIONS = ("东部", "中部", "西部", "东北")
_PAGE_GROUPS = {
    7: ("P2-1.1", "P2-1.2", ("轿车", "SUV", "MPV", "交叉型乘用车")),
    8: ("P2-2.1", "P2-2.2", ("A00", "A0", "A", "B", "C+")),
    12: ("P2-6.1", "P2-6.2", ("自主", "美系", "欧系", "日系", "韩系")),
    13: ("P2-7.1", "P2-7.2", ("10万以下", "10-15万", "15-20万", "20-25万", "25-35万", "35万以上")),
    15: ("P2-9.1", "P2-9.2", ("一线城市", "新一线城市", "二线城市", "三线城市", "四线城市", "五线城市")),
}


def _previous(month: str) -> str:
    year, number = map(int, month.split("-"))
    return f"{year - 1}-12" if number == 1 else f"{year}-{number - 1:02d}"


def _prior(month: str) -> str:
    return f"{int(month[:4]) - 1}-{month[5:]}"


def _views(text: str):
    for view in str(text).split("---视图分段---"):
        # Do not deduplicate repeated labels or identical adjacent values.
        yield [line.strip() for line in view.splitlines() if line.strip()]


def _warn(warnings: list[dict], code: str, reason: str, **details) -> None:
    item = {"card_code": code, "reason": reason, **details}
    if item not in warnings:
        warnings.append(item)


def _put(rows: dict, key: str, value: dict, conflicts: set, warnings: list, code: str) -> None:
    if key in conflicts:
        return
    if key in rows and rows[key] != value:
        rows.pop(key)
        conflicts.add(key)
        _warn(warnings, code, "conflicting_complete_rows", period_or_entity=key)
    else:
        rows[key] = value


def _wide(text: str, code: str, entities: tuple[str, ...], warnings: list,
          kind: str = "month", years: tuple[str, ...] = ()) -> dict[str, dict[str, int]]:
    """Quantity-first rows with an explicit axis and complete entity headers."""
    pattern = {"month": _MONTH, "year": _YEAR, "bare_month": _BARE_MONTH}[kind]
    axes = {"month": ("日期组合 (月)", "库存日期"),
            "year": ("年", "日期组合 (年)"), "bare_month": ("月",)}[kind]
    rows, conflicts = {}, set()
    for lines in _views(text):
        axis = next((lines.index(label) for label in axes if label in lines), None)
        if axis is None:
            continue
        start = next((i for i in range(axis + 1, len(lines)) if pattern.fullmatch(lines[i])), None)
        if start is None:
            continue
        names = [value for value in lines[axis + 1:start] if value in entities]
        quantity_count = sum(value in _QUANTITY_HEADERS for value in lines[1:axis])
        if len(entities) == 1 and not names:
            quantity_count = sum(value in _QUANTITY_HEADERS for value in lines[1:start])
            if quantity_count != 1:
                continue
        elif quantity_count != len(entities) or names[:len(entities)] != list(entities):
            continue  # Horizontal fragments must not become a complete group.
        def is_period(value: str) -> bool:
            return bool(pattern.fullmatch(value)) and (kind != "year" or not years or value in years)
        indices = [i for i in range(start, len(lines)) if is_period(lines[i])]
        for position, index in enumerate(indices):
            end = indices[position + 1] if position + 1 < len(indices) else len(lines)
            values = []
            for value in lines[index + 1:end]:
                if not _INTEGER.fullmatch(value):
                    break
                values.append(int(value.replace(",", "")))
            if len(values) != quantity_count:
                _warn(warnings, code, "incomplete_quantity_row", period=lines[index],
                      expected_cells=quantity_count, observed_cells=len(values))
                continue
            _put(rows, lines[index], dict(zip(entities, values)), conflicts, warnings, code)
    return rows


def _entities(text: str, code: str, month: str, warnings: list, cumulative: bool = False,
              provinces: bool = False) -> dict[str, dict[str, Any]]:
    """Entity rows use the complete 4-period (or 2-year) quantity header."""
    expected = [str(int(month[:4]) - 1), month[:4]] if cumulative or provinces else [
        _previous(_prior(month)), _prior(month), _previous(month), month]
    result, conflicts = {}, set()
    label = "使用省份" if provinces else "企业简称"
    for lines in _views(text):
        if label not in lines:
            continue
        if sum(value in _QUANTITY_HEADERS for value in lines[1:lines.index(label)]) != len(expected):
            _warn(warnings, code, "quantity_header_count_mismatch", expected_cells=len(expected))
            continue
        start = lines.index(label) + 1
        header = []
        while start < len(lines) and (_MONTH.fullmatch(lines[start]) or _YEAR.fullmatch(lines[start])):
            header.append(lines[start])
            start += 1
        if header[:len(expected)] != expected:
            _warn(warnings, code, "period_header_mismatch", expected_periods=expected, observed_periods=header[:len(expected)])
            continue
        region = None
        index = start
        while index < len(lines):
            name = lines[index]
            if name.startswith(("加载", "已追加")):
                break
            if provinces and name in _REGIONS:
                region = name
                index += 1
                if index >= len(lines):
                    break
                name = lines[index]
            if _INTEGER.fullmatch(name) or "%" in name or name == "-":
                index += 1
                continue
            index += 1
            values = []
            while index < len(lines) and _INTEGER.fullmatch(lines[index]):
                values.append(int(lines[index].replace(",", "")))
                index += 1
            while index < len(lines) and ("%" in lines[index] or lines[index] == "-"):
                index += 1
            if len(values) != len(expected):
                _warn(warnings, code, "incomplete_entity_row", entity=name,
                      expected_cells=len(expected), observed_cells=len(values))
                continue
            row = {"values": dict(zip(expected, values))}
            if provinces:
                row["region"] = region
            _put(result, name, row, conflicts, warnings, code)
    return result


def _energy_months(text: str, warnings: list) -> dict[str, dict[str, int]]:
    """Bind each quantity to BOTH the year and energy headers, before shares."""
    code = "P2-11.1"
    rows, conflicts = {}, set()
    for lines in _views(text):
        if "月" not in lines:
            continue
        axis = lines.index("月")
        years = [value for value in lines[1:axis] if _YEAR.fullmatch(value)]
        count = sum(value == "数量" for value in lines[1:axis])
        first = next((i for i in range(axis + 1, len(lines)) if _BARE_MONTH.fullmatch(lines[i])), None)
        if first is None or count != 4 or len(years) < count:
            continue
        names = lines[axis + 1:first][:count]
        pairs = list(zip(years[:count], names))
        if pairs != [(years[0], "传统车"), (years[1], "传统车"),
                     (years[0], "新能源"), (years[1], "新能源")] or years[0] == years[1]:
            continue
        indices = [i for i in range(first, len(lines)) if _BARE_MONTH.fullmatch(lines[i])]
        for position, index in enumerate(indices):
            end = indices[position + 1] if position + 1 < len(indices) else len(lines)
            values = []
            for value in lines[index + 1:end]:
                if not _INTEGER.fullmatch(value):
                    break
                values.append(int(value.replace(",", "")))
            if len(values) != count:
                _warn(warnings, code, "incomplete_year_energy_row", month=lines[index],
                      expected_cells=count, observed_cells=len(values))
                continue
            for year in dict.fromkeys(years[:count]):
                row = {entity: value for (column_year, entity), value in zip(pairs, values) if column_year == year}
                _put(rows, f"{year}-{lines[index]}", row, conflicts, warnings, code)
    return rows


def _strict_energy_yoy_cells(text: str, warnings: list) -> dict[str, dict[str, dict]]:
    """Read direct BI rates only when every explicitly named cell is present."""
    code = "P2-12.1"
    result, conflicts = {}, set()
    metrics = ["数量", "数量", "同比", "同比", "份额", "份额"]
    names = ["插电式混合动力", "纯电动"] * 3
    for lines in _views(text):
        if "日期组合 (月)" not in lines:
            continue
        axis = lines.index("日期组合 (月)")
        first = next((i for i in range(axis + 1, len(lines)) if _MONTH.fullmatch(lines[i])), None)
        if first is None or lines[1:axis] != metrics or lines[axis + 1:first] != names:
            continue
        indices = [i for i in range(first, len(lines)) if _MONTH.fullmatch(lines[i])]
        for position, index in enumerate(indices):
            end = indices[position + 1] if position + 1 < len(indices) else len(lines)
            cells = lines[index + 1:end]
            if len(cells) != 6 or not all(_INTEGER.fullmatch(value) for value in cells[:2]) or not all(_PERCENT.fullmatch(value) for value in cells[2:]):
                continue
            row = {}
            for column, entity in enumerate(("PHEV", "BEV")):
                row[entity] = {"value": int(cells[column].replace(",", "")),
                               "observed_yoy_pct": float(_PERCENT.fullmatch(cells[column + 2])[1]),
                               "percent_operands": {"source_card_code": code, "period": lines[index],
                                                    "header": metrics, "entity_header": names,
                                                    "index": column + 2, "raw_cell": cells[column + 2],
                                                    "raw_cells": cells}}
            _put(result, lines[index], row, conflicts, warnings, code)
    return result


def _regions(text: str, warnings: list, month: str, national: dict) -> dict[str, dict[str, int]]:
    code = "P2-8.2"
    entities = _entities(text.replace("区域-使用", "企业简称"), code, month, warnings, cumulative=True)
    if set(entities) != set(_REGIONS):
        _warn(warnings, code, "incomplete_region_universe", observed_entities=sorted(entities))
        return {}
    rows = {f"{year}-{month[5:]}": {entity: row["values"][year] for entity, row in entities.items()}
            for year in (str(int(month[:4]) - 1), month[:4])}
    if any(sum(values.values()) != national.get(period, {}).get("整体市场") for period, values in rows.items()):
        _warn(warnings, code, "year_table_not_verified_as_target_month",
              totals={period: sum(values.values()) for period, values in rows.items()})
        return {}
    return rows


def _rate(current: int | float, baseline: int | float) -> float | None:
    return round((current / baseline - 1) * 100, 1) if baseline else None


def _fid(code: str, entity: str, scope: str, period: str) -> str:
    return f"{code}:{entity}:{scope}:{period}"


class _Packet:
    def __init__(self, page: int, cards: dict, month: str):
        self.page, self.cards, self.month = page, cards, month
        self.warnings: list[dict] = []
        self.facts: list[dict] = []
        self.groups: list[dict] = []
        self.national = self.wide("P1.1-1", ("整体市场",))
        self.national_ytd = self.wide("P1.1-3", ("整体市场",), "year")

    def text(self, code: str) -> str:
        return str(self.cards.get(code, {}).get("text", ""))

    def wide(self, code: str, entities: tuple, kind: str = "month") -> dict:
        return _wide(self.text(code), code, entities, self.warnings, kind,
                     (str(int(self.month[:4]) - 1), self.month[:4]))

    def totals(self, scope: str, energy: bool = False) -> dict:
        if energy:
            if scope == "year_to_date":
                values = self.wide("P2-11.2", ("传统车", "新能源"), "year")
                return {f"{year}-{self.month[5:]}": row["新能源"] for year, row in values.items()}
            return {period: row["新能源"] for period, row in _energy_months(self.text("P2-11.1"), self.warnings).items()}
        if scope == "year_to_date":
            return {f"{year}-{self.month[5:]}": row["整体市场"] for year, row in self.national_ytd.items()}
        return {period: row["整体市场"] for period, row in self.national.items()}

    def add_group(self, code: str, rows: dict, entities: tuple, scope: str = "single_month",
                  metric: str = "sales", share_scope: str = "passenger_market",
                  totals: dict | None = None, observed_only: bool = False,
                  extra: dict | None = None) -> None:
        target = self.month
        if scope == "year_to_date":
            rows = {f"{year}-{target[5:]}": values for year, values in rows.items()}
        comparison = rows.get(_prior(target), {})
        current = rows.get(target, {})
        previous = rows.get(_previous(target), {}) if scope != "year_to_date" else {}
        complete = set(current) == set(entities) and bool(current) and not observed_only
        comparison_complete = complete and set(comparison) == set(entities)
        if totals is None:
            totals = {period: sum(values.values()) for period, values in rows.items()
                      if set(values) == set(entities) and not observed_only}
        denominator_code = None
        denominator_entity = "整体市场"
        denominator_scope = scope
        if observed_only and share_scope == "passenger_market":
            denominator_code = "P1.1-3" if scope == "year_to_date" else "P1.1-1"
        elif share_scope == "nev_market" and totals:
            denominator_code = "P2-11.2" if scope == "year_to_date" else "P2-11.1"
            denominator_entity = "新能源"
        elif metric == "inventory" and code != "P1.2-1":
            denominator_code, denominator_entity = "P1.2-1", "行业库存"
        group = {"card_code": code, "scope": scope, "period": target,
                 "expected_entities": list(entities), "observed_entities": list(current),
                 "complete": complete, "comparison_complete": comparison_complete,
                 "previous_complete": complete and set(previous) == set(entities),
                 "superlatives_allowed": comparison_complete, "ranking_scope": "observed_only" if observed_only else "complete_group",
                 "observed_periods": sorted(rows), "share_scope": share_scope}
        comparable_yoy = comparison_complete and all(comparison[entity] > 0 for entity in entities)
        comparable_mom = complete and set(previous) == set(entities) and all(previous[entity] > 0 for entity in entities)
        group["superlatives_allowed"] = comparable_yoy
        group["superlatives_by_metric"] = {"value": complete, "share_pct": complete and bool(totals.get(target)),
                                           "yoy_pct": comparable_yoy, "mom_pct": comparable_mom}
        if target in totals:
            group["total_value"] = totals[target]
        self.groups.append(group)
        if not current:
            _warn(self.warnings, code, "missing_target_period", period=target, scope=scope)
        for period, values in sorted(rows.items()):
            if period > target:
                continue
            baseline = rows.get(_prior(period), {})
            earlier = rows.get(_previous(period), {}) if scope != "year_to_date" else {}
            for entity, value in values.items():
                record = {"fact_id": _fid(code, entity, scope, period), "source_card_code": code,
                          "entity": entity, "scope": scope, "period": period,
                          "metric": metric, "value": value, "unit": "辆", "share_scope": share_scope,
                          "source_fact_ids": [_fid(code, entity, scope, period)],
                          "operands": {"current_value": value}, "method": "complete quantity row with explicit period/entity headers"}
                if scope == "year_to_date":
                    record["period_start"] = f"{period[:4]}-01"
                    record["period_end"] = period
                    record["method"] = "complete year-labelled cumulative quantity row bound to report-month filter; not full-year totals"
                if extra and entity in extra:
                    record.update(extra[entity])
                for field, comparison_values, comparison_period, delta, rate in (
                    ("comparison_value", baseline, _prior(period), "delta_yoy", "yoy_pct"),
                    ("previous_value", earlier, _previous(period), "delta_mom", "mom_pct"),
                ):
                    if entity not in comparison_values:
                        continue
                    operand = comparison_values[entity]
                    record.update({field: operand, delta: value - operand})
                    record["operands"][field] = operand
                    record["source_fact_ids"].append(_fid(code, entity, scope, comparison_period))
                    result = _rate(value, operand)
                    if result is not None:
                        record[rate] = result
                    record["method"] += f"; {delta}=current_value-{field}; {rate}=round((current_value/{field}-1)*100,1)"
                if "comparison_value" in record:
                    comparison_scope = "prior_year_same_period" if scope == "year_to_date" else "prior_year_same_month"
                    record["comparison_scope"] = comparison_scope
                    record[f"{'inventory' if metric == 'inventory' else 'sales'}_comparison_scope"] = comparison_scope
                    record["comparison_period"] = _prior(period)
                if "previous_value" in record:
                    record["previous_period"] = _previous(period)
                total = totals.get(period)
                if total:
                    record["share_pct"] = round(value / total * 100, 1)
                    record["operands"]["total_value"] = total
                    record["method"] += "; share_pct=round(current_value/total_value*100,1)"
                    record["denominator_value"] = total
                    record["denominator_source_fact_ids"] = (
                        [_fid(denominator_code, denominator_entity, denominator_scope, period)] if denominator_code else
                        [_fid(code, member, scope, period) for member in values])
                    record["source_fact_ids"].extend(value for value in record["denominator_source_fact_ids"]
                                                   if value not in record["source_fact_ids"])
                for prefix, compared, compared_period in (
                    ("previous", earlier, _previous(period)), ("comparison", baseline, _prior(period)),
                ):
                    compared_total = totals.get(compared_period)
                    if total and compared_total and entity in compared:
                        record[f"{prefix}_share_pct"] = round(compared[entity] / compared_total * 100, 1)
                        record["operands"][f"{prefix}_total_value"] = compared_total
                        record["source_fact_ids"].extend(
                            [_fid(denominator_code, denominator_entity, denominator_scope, compared_period)] if denominator_code else
                            [_fid(code, member, scope, compared_period) for member in compared]
                        )
                share_basis = "previous" if "previous_share_pct" in record else "comparison"
                if "share_pct" in record and f"{share_basis}_share_pct" in record:
                    basis_values = earlier if share_basis == "previous" else baseline
                    basis_period = _previous(period) if share_basis == "previous" else _prior(period)
                    record["share_change_pp"] = round((value / total - basis_values[entity] / totals[basis_period]) * 100, 1)
                    record["share_comparison_scope"] = ("previous_month" if share_basis == "previous" else
                                                        "prior_year_same_period" if scope == "year_to_date" else "prior_year_same_month")
                    record["method"] += f"; share_change_pp=round((current_value/total_value-{share_basis}_value/{share_basis}_total_value)*100,1)"
                record["source_fact_ids"] = list(dict.fromkeys(record["source_fact_ids"]))
                self.facts.append(record)

    def bare_sales(self, code: str, entities: tuple) -> dict:
        rows = self.wide(code, entities, "bare_month")
        result = {}
        for number, values in rows.items():
            period = f"{self.month[:4]}-{number}"
            if sum(values.values()) == self.national.get(period, {}).get("整体市场"):
                result[period] = values
            else:
                _warn(self.warnings, code, "bare_month_year_not_verified", month=number)
        return result

    def add_enterprises(self, code: str, scope: str, energy: bool = False) -> None:
        source = _entities(self.text(code), code, self.month, self.warnings, scope == "year_to_date")
        rows = {}
        for entity, record in source.items():
            for period, value in record["values"].items():
                rows.setdefault(period, {})[entity] = value
        totals = self.totals(scope, energy)
        self.add_group(code, rows, tuple(source), scope, totals=totals, observed_only=True,
                       share_scope="nev_market" if energy else "passenger_market")
        current = [row for row in self.facts if row["source_card_code"] == code and row["period"] == self.month]
        for row in current:
            row["rank_in_observed"] = 1 + sum(other["value"] > row["value"] for other in current)
            row["ranking_scope"] = "observed_only"
            row["operands"]["observed_rank_values"] = {other["entity"]: other["value"] for other in current}
            row["source_fact_ids"] = list(dict.fromkeys([*row["source_fact_ids"], *(other["fact_id"] for other in current)]))
            row["method"] += "; rank_in_observed=1+count(observed current value>current_value); not global ranking"


def page_business_facts(page: int, cards: dict, month: str) -> dict[str, Any]:
    """Return local typed facts, explicit comparison coverage and warnings.

    The full packet is for validators. Editors should receive only facts used
    by their selected draft. Year-only tables describe the selected month/YTD
    filter, never a whole year; the region filter is additionally verified by
    matching both national same-month totals.
    """
    if not _MONTH.fullmatch(month):
        raise ValueError("report month must be YYYY-MM")
    packet = _Packet(page, cards, month)
    if page == 4:
        packet.add_group("P1.1-1", packet.national, ("整体市场",))
        packet.add_group("P1.1-3", packet.national_ytd, ("整体市场",), "year_to_date")
        reference_values = set()
        for lines in _views(packet.text("P1.1-2")):
            if "月" not in lines or "历史月均字段" not in lines:
                continue
            for index, value in enumerate(lines[:-1]):
                if value == month[5:] and re.fullmatch(r"\d+(?:\.\d+)?", lines[index + 1]):
                    reference_values.add(float(lines[index + 1]))
        if len(reference_values) == 1:
            reference = reference_values.pop()
            record = {"fact_id": _fid("P1.1-2", "历史月均", "history_reference", month),
                      "entity": "历史月均", "scope": "history_reference", "period": month,
                      "metric": "reference_sales", "value": reference, "unit": "万辆",
                      "source_card_code": "P1.1-2", "reference_period": "2025年之前历史月均",
                      "source_fact_ids": [_fid("P1.1-2", "历史月均", "history_reference", month)],
                      "operands": {"reference_month": month[5:], "reference_sales": reference},
                      "method": "explicit historical calendar-month reference; not target-month actual sales"}
            packet.facts.append(record)
        elif reference_values:
            _warn(packet.warnings, "P1.1-2", "conflicting_history_reference", month=month[5:])
        elif packet.text("P1.1-2"):
            _warn(packet.warnings, "P1.1-2", "missing_requested_history_reference", month=month[5:])
    elif page == 5:
        packet.add_group("P1.1-1", packet.national, ("整体市场",))
        inventory = packet.wide("P1.2-1", ("行业库存",))
        stock_totals = {period: row["行业库存"] for period, row in inventory.items()}
        packet.add_group("P1.2-1", inventory, ("行业库存",), "stock", "inventory", "industry_stock")
        for code, entities in (("P1.2-2A", ("新能源", "传统车")), ("P1.2-2C", ("合资", "自主"))):
            packet.add_group(code, packet.wide(code, entities), entities, "stock", "inventory", "industry_stock", stock_totals)
        for code, entities in (("P1.2-2B", ("新能源", "传统车")), ("P1.2-2D", ("合资", "自主"))):
            packet.add_group(code, packet.bare_sales(code, entities), entities)
            for row in packet.facts:
                if row["source_card_code"] != code:
                    continue
                row["period_verified_by"] = "bare calendar month quantities sum to the explicitly dated national same-month total"
                row["method"] = "calendar-month quantity header; year verified by national dated total; " + row["method"]
                row["operands"]["year_binding_national_total"] = packet.national[row["period"]]["整体市场"]
                row["source_fact_ids"].append(_fid("P1.1-1", "整体市场", "single_month", row["period"]))
    elif page in _PAGE_GROUPS:
        single, cumulative, entities = _PAGE_GROUPS[page]
        packet.add_group(single, packet.wide(single, entities), entities)
        packet.add_group(cumulative, packet.wide(cumulative, entities, "year"), entities, "year_to_date")
    elif page == 14:
        rows = _regions(packet.text("P2-8.2"), packet.warnings, month, packet.national)
        packet.add_group("P2-8.2", rows, _REGIONS,
                         extra={entity: {"period_verified_by": "both year-column region totals match dated national same-month totals"}
                                for entity in _REGIONS})
        packet.add_group("P1.1-1", packet.national, ("整体市场",))
        provinces = _entities(packet.text("P2-8.1"), "P2-8.1", month, packet.warnings, provinces=True)
        if rows:
            provincial_rows = {}
            for entity, record in provinces.items():
                for year, value in record["values"].items():
                    provincial_rows.setdefault(f"{year}-{month[5:]}", {})[entity] = value
            packet.add_group("P2-8.1", provincial_rows, tuple(provinces), observed_only=True,
                             totals=packet.totals("single_month"),
                             extra={entity: {"region": row.get("region"), "period_verified_by": "P2-8.2 same-month national totals"}
                                    for entity, row in provinces.items()})
        else:
            _warn(packet.warnings, "P2-8.1", "province_year_table_scope_unverified")
    elif page in (16, 19):
        group = "10" if page == 16 else "13"
        for suffix, scope in (("1", "single_month"), ("2", "year_to_date")):
            packet.add_enterprises(f"P2-{group}.{suffix}", scope, page == 19)
    elif page == 17:
        entities = ("传统车", "新能源")
        packet.add_group("P2-11.1", _energy_months(packet.text("P2-11.1"), packet.warnings), entities)
        packet.add_group("P2-11.2", packet.wide("P2-11.2", entities, "year"), entities, "year_to_date")
    elif page == 18:
        names = ("插电式混合动力", "纯电动")
        aliases = {"插电式混合动力": "PHEV", "纯电动": "BEV"}
        for code, scope in (("P2-12.1", "single_month"), ("P2-12.3", "year_to_date")):
            kind = "year" if scope == "year_to_date" else "month"
            raw = packet.wide(code, names, kind)
            rows = {period: {aliases[entity]: value for entity, value in values.items()} for period, values in raw.items()}
            nev_totals = packet.totals(scope, energy=True)
            packet.add_group(code, rows, ("PHEV", "BEV"), scope,
                             share_scope="nev_market" if nev_totals else "bev_phev_market",
                             totals=nev_totals or None)
            if scope == "single_month":
                observed = _strict_energy_yoy_cells(packet.text(code), packet.warnings)
                for row in packet.facts:
                    if row["source_card_code"] != code:
                        continue
                    cell = observed.get(row["period"], {}).get(row["entity"])
                    if not cell or cell["value"] != row["value"]:
                        continue
                    if "yoy_pct" in row and abs(row["yoy_pct"] - cell["observed_yoy_pct"]) > 0.051:
                        _warn(packet.warnings, code, "direct_percentage_disagrees_with_quantity_derivation",
                              period=row["period"], entity=row["entity"])
                        continue
                    row["observed_yoy_pct"] = cell["observed_yoy_pct"]
                    row["percent_operands"] = cell["percent_operands"]
                    if "yoy_pct" not in row:
                        row["yoy_pct"] = cell["observed_yoy_pct"]
                        row["source_method"] = "direct BI percent cell"
                        row["yoy_source_method"] = "direct BI percent cell"
                        row["method"] += "; yoy_pct=explicit BI同比 cell with complete 2-quantity/2-yoy/2-share headers and cells; no comparison quantity inferred"
        # The five-energy share-only viewport omits cells. PHEV/BEV overall
        # shares can still be derived independently from their explicit sales.
        sales = {row["period"]: {} for row in packet.facts if row["scope"] == "single_month"}
        for row in packet.facts:
            if row["scope"] == "single_month":
                sales[row["period"]][row["entity"]] = row["value"]
        start = len(packet.facts)
        packet.add_group("P2-12.2", sales, ("PHEV", "BEV", "燃料电池", "传统燃料", "常规混合动力"),
                         totals=packet.totals("single_month"), share_scope="passenger_market", observed_only=True)
        for row in packet.facts[start:]:
            periods = [row["period"]]
            if "comparison_value" in row:
                periods.append(_prior(row["period"]))
            if "previous_value" in row:
                periods.append(_previous(row["period"]))
            row["source_fact_ids"] = [fact_id for period in periods for fact_id in (
                _fid("P2-12.1", row["entity"], "single_month", period),
                _fid("P1.1-1", "整体市场", "single_month", period))]
            row["method"] = "PHEV/BEV quantities from P2-12.1; passenger-market denominator from P1.1-1; " + row["method"]
        _warn(packet.warnings, "P2-12.2", "share_only_view_not_used_to_infer_missing_fuel_cells")
    else:
        raise ValueError(f"unsupported monthly-report page: {page}")
    return {"business_facts": packet.facts,
            "coverage": {"page": page, "period": month, "groups": packet.groups,
                         "has_target_period_facts": any(row["period"] == month for row in packet.facts),
                         "all_required_groups_complete": bool(packet.groups) and all(row["complete"] for row in packet.groups)},
            "fact_warnings": packet.warnings}
