# -*- coding: utf-8 -*-
"""Small reviewed economic-identity gates; never rewrite publisher actuals.

Inputs are rebuilt chart ledgers and already validated source observations.
Template archival values are not proof.  GDP demand contributions are quarterly
cumulative growth contributions, NOT the separate quarterly-YoY GDP chart.
"""
from __future__ import annotations

from datetime import date
import math

from macro_contract import parse_period


GDP_ID = "s10-shape28"
GDP_ROLES = (
    ("consumption", "消费支出拉动", "百分点"),
    ("capital", "资本形成拉动", "百分点"),
    ("net_exports", "货物和服务净出口拉动", "百分点"),
    ("gdp_cumulative", "GDP:累计同比", "%"),
)
CUMULATIVE_AMOUNTS = {
    "s14-shape15": ("固定资产投资累计值", "民间固定资产投资累计值"),
    "s30-shape13": ("财政收入(万亿)", "财政支出(万亿)"),
}


def _number(value):
    return (float(value) if isinstance(value, (int, float)) and not isinstance(value, bool)
            and math.isfinite(value) else None)


def _date(value, frequency):
    try:
        return parse_period(value, frequency)
    except (ValueError, TypeError):
        return None


def _named(chart, name):
    return next((series for series in chart.get("series", [])
                 if series.get("original_name", series.get("name")) == name), None)


def _verified(series, observations, frequency):
    """Use caller-replayed sources; never promote archival actual_values."""
    if not series:
        return {}
    if observations is None:
        points = series.get("verified_points", [])
    elif isinstance(observations, dict):
        points = [point for rid in series.get("request_ids", [])
                  for point in observations.get(rid, [])]
    else:
        rids = set(series.get("request_ids", []))
        points = [point for point in observations if point.get("request_id") in rids]
    result = {}
    for point in points:
        day = _date(point.get("date", point.get("period")), frequency)
        value = _number(point.get("value"))
        if day and value is not None:
            result[day] = value
    return result


def _at(series, day, index, verified):
    if series is None:
        return None, "missing"
    actuals, forecasts = series.get("actual_values", []), series.get("forecast_values", [])
    actual = _number(actuals[index]) if index < len(actuals) else None
    forecast = _number(forecasts[index]) if index < len(forecasts) else None
    if day in verified and actual is not None:
        return verified[day], "actual_and_forecast" if forecast is not None else "actual"
    if forecast is not None:
        return forecast, "forecast"
    return None, "archival" if actual is not None else "missing"


def _gdp(chart, observations):
    issues = []
    dates = [_date(raw, "quarterly") for raw in chart.get("categories", [])]
    target = _date(chart.get("target"), "quarterly")
    series = {role: _named(chart, name) for role, name, _ in GDP_ROLES}
    proof = {role: _verified(item, observations, "quarterly") for role, item in series.items()}
    actual_dates = [day for points in proof.values() for day in points]
    baseline = max(actual_dates) if actual_dates else None
    wrong_units = {role: item.get("unit") for role, _, unit in GDP_ROLES
                   if (item := series[role]) is not None and item.get("unit") != unit}
    if wrong_units:
        issues.append({"code": "gdp_decomposition_unit_mismatch", "chart_id": GDP_ID,
                       "date": target.isoformat() if target else None,
                       "series": wrong_units, "actual_vs_forecast": "unverified_unit",
                       "component_sum": None, "gdp_cumulative": None, "delta": None})
    considered = set()
    for index, day in enumerate(dates):
        if day is None:
            continue
        entries = {role: _at(item, day, index, proof[role]) for role, item in series.items()}
        # Publisher history lengths naturally differ. Only the target, newest
        # actual baseline, or fully proven same-period history is an identity
        # claim. An older GDP-only source row cannot promote the other archived
        # components, but does not by itself block an otherwise complete report.
        complete_period = all(status in {"actual", "forecast", "actual_and_forecast"}
                              for _, status in entries.values())
        active = day in {target, baseline} or complete_period
        if not active:
            continue
        considered.add(day)
        statuses = {role: status for role, (_, status) in entries.items()}
        values = {role: value for role, (value, _) in entries.items()}
        missing = [role for role, value in values.items() if value is None or role in wrong_units]
        complete = not missing
        total = sum(values[role] for role, _, _ in GDP_ROLES[:3]) if complete else None
        gdp = values["gdp_cumulative"]
        delta = total - gdp if complete else None
        common = {"chart_id": GDP_ID, "date": day.isoformat(), "series": values,
                  "actual_vs_forecast": statuses, "component_sum": total,
                  "gdp_cumulative": gdp, "delta": delta}
        if missing:
            issues.append({"code": "gdp_decomposition_incomplete", "missing": missing, **common})
        if any(status == "actual_and_forecast" for status in statuses.values()):
            issues.append({"code": "gdp_actual_forecast_overlap", **common})
        # Four one-decimal publisher values each carry <=0.05 rounding error.
        if complete and abs(delta) > 0.2 + 1e-9:
            issues.append({"code": "gdp_decomposition_mismatch", "tolerance_pp": 0.2, **common})
    if target and target not in considered:
        issues.append({"code": "gdp_decomposition_target_missing", "chart_id": GDP_ID,
                       "date": target.isoformat(), "series": {}, "actual_vs_forecast": "missing",
                       "component_sum": None, "gdp_cumulative": None, "delta": None})
    if baseline and baseline not in considered:
        issues.append({"code": "gdp_decomposition_baseline_missing", "chart_id": GDP_ID,
                       "date": baseline.isoformat(), "series": {}, "actual_vs_forecast": "actual",
                       "component_sum": None, "gdp_cumulative": None, "delta": None})
    return issues


def _cumulative(chart, observations):
    issues = []
    cid = chart["chart_id"]
    dates = [_date(raw, "monthly") for raw in chart.get("categories", [])]
    for name in CUMULATIVE_AMOUNTS[cid]:
        series = _named(chart, name)
        if series is None:
            continue  # structural/native-series gate owns missing chart roles
        forecasts = series.get("forecast_values", [])
        predicted = {day: _number(forecasts[index]) for index, day in enumerate(dates)
                     if day and index < len(forecasts) and forecasts[index] is not None}
        if not predicted:
            continue
        if series.get("unit") != "亿元":
            issues.append({"code": "cumulative_amount_unit_mismatch", "chart_id": cid,
                           "date": chart.get("target"), "series": name,
                           "actual_vs_forecast": "forecast", "component_sum": None,
                           "delta": None, "unit": series.get("unit")})
            continue
        actual = _verified(series, observations, "monthly")
        earlier_forecasts = {}
        for day, value in sorted(predicted.items()):
            common = {"chart_id": cid, "date": day.isoformat(), "series": name,
                      "actual_vs_forecast": "forecast", "forecast_value": value,
                      "component_sum": None, "delta": None}
            if value is None:
                issues.append({"code": "cumulative_forecast_nonfinite", **common})
                continue
            if day in actual:
                issues.append({"code": "cumulative_actual_forecast_overlap", "actual_value": actual[day], **common})
            known = [(period, amount) for period, amount in actual.items() if period < day]
            if not known:
                issues.append({"code": "cumulative_forecast_baseline_missing", **common})
                earlier_forecasts[day] = value
                continue
            last_actual, last_value = max(known)
            # None of the current statistical baselines models a cumulative
            # year reset. Forecasts into a new year cannot impersonate one.
            if last_actual.year != day.year:
                issues.append({"code": "cumulative_forecast_cross_year_unmodeled",
                               "baseline_date": last_actual.isoformat(), "baseline_value": last_value,
                               "delta": value - last_value, **{k: v for k, v in common.items() if k != "delta"}})
            previous = [(period, amount, "actual") for period, amount in actual.items()
                        if period < day and period.year == day.year]
            previous += [(period, amount, "forecast") for period, amount in earlier_forecasts.items()
                         if period < day and period.year == day.year]
            if previous:
                period, amount, status = max(previous, key=lambda point: point[0])
                if value < amount - 1e-8:
                    issues.append({"code": "cumulative_forecast_decrease", "previous_date": period.isoformat(),
                                   "previous_value": amount, "previous_status": status, "delta": value - amount,
                                   **{k: v for k, v in common.items() if k != "delta"}})
            earlier_forecasts[day] = value
    return issues


def validate_constraints(charts, observations):
    """Return explicit violations; never balance numbers or mutate inputs."""
    issues = []
    for chart in charts:
        if chart.get("chart_id") == GDP_ID:
            issues.extend(_gdp(chart, observations))
        elif chart.get("chart_id") in CUMULATIVE_AMOUNTS:
            issues.extend(_cumulative(chart, observations))
    return issues
