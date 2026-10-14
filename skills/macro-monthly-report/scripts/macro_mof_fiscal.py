"""Replay national general-budget cumulative amounts and growth from MOF.

Only four reviewed series, from the national budget section of an original
Treasury release. Provincial budgets, government funds and monthly flows are
not aliases for these observations.
"""
import calendar
from datetime import date
from hashlib import sha256
import math
import re
from urllib.parse import urlparse

PROFILE = "mof_national_general_budget_v1"
ROLES = {
    "s30-shape13::财政收入(万亿)": ("收入", "amount", "亿元"),
    "s30-shape13::财政支出(万亿)": ("支出", "amount", "亿元"),
    "s30-shape13::财政收入增速（右轴）": ("收入", "growth", "%"),
    "s30-shape13::财政支出增速（右轴）": ("支出", "growth", "%"),
}
METADATA = {"series_name", "receipt_id", "published_at", "source_url", "source_grade", "publisher_id"}
NUMBER = r"[+-]?\d+(?:\.\d+)?"


def compact(value):
    return re.sub(r"\s+", "", str(value))


def _request(request):
    role = ROLES.get(request.get("id"))
    if not role:
        raise ValueError("mof_fiscal_request_not_reviewed")
    series = request["id"].split("::", 1)[1]
    if (request.get("chart_id") != "s30-shape13" or request.get("series_name") != series
            or request.get("definition") != "一般公共预算累计收支：" + series
            or request.get("unit") != role[2] or request.get("frequency") != "monthly"
            or set(request.get("definition_aliases", [])) != {"一般公共预算" + role[0]}
            or "mof.gov.cn" not in request.get("original_publisher_domains", request.get("source_domains", []))):
        raise ValueError("mof_fiscal_request_not_reviewed")
    return role


def _receipt(page):
    parsed = urlparse(page["url"])
    if parsed.scheme != "https" or parsed.hostname != "gks.mof.gov.cn":
        raise ValueError("mof_fiscal_original_department_unproven")
    if (not page.get("receipt_id") or page.get("truncated")
            or sha256(page["text"].encode()).hexdigest() != page.get("text_sha256")):
        raise ValueError("mof_fiscal_receipt_changed")
    published = date.fromisoformat(page["published_at"])
    matches = list(re.finditer(r"(20\d{2})年\s*(\d{1,2})月\s*(\d{1,2})日[^\S\r\n]*来源[：:]国库司", page["text"]))
    if (len(matches) != 1 or date(*(int(part) for part in matches[0].groups())) != published):
        raise ValueError("mof_fiscal_publication_not_literal")
    return published


def _candidates(page, requests):
    text = page["text"]
    title = text.splitlines()[0].strip()
    found = re.fullmatch(r"(20\d{2})年(上半年|1[-—－](\d{1,2})月)财政收支情况", compact(title))
    if not found:
        return []
    year, month = int(found[1]), 6 if found[2] == "上半年" else int(found[3])
    if not 2 <= month <= 12:
        return []
    period = f"{year}-{month:02d}"
    headers = list(re.finditer(r"一、全国一般公共预算收支情况", text))
    ends = list(re.finditer(r"二、全国政府性基金预算收支情况", text))
    if len(headers) != 1 or len(ends) != 1 or ends[0].start() <= headers[0].end():
        return []
    section = text[headers[0].end():ends[0].start()]
    marker = "上半年" if found[2] == "上半年" else rf"1[-—－]{month}月"
    result = []
    for request in requests:
        try:
            direction, metric, unit = _request(request)
        except (ValueError, TypeError, KeyError):
            continue
        subheading = rf"[（(]{'一' if direction == '收入' else '二'}[）)]一般公共预算{direction}情况[。.]?"
        starts = list(re.finditer(subheading, section))
        if len(starts) != 1:
            continue
        stop = re.search(r"[（(]二[）)]一般公共预算支出情况", section[starts[0].end():]) if direction == "收入" else None
        substart = starts[0].end()
        subend = substart + stop.start() if stop else len(section)
        body = section[substart:subend]
        pattern = rf"(?P<marker>{marker})[，,]\s*全国一般公共预算{direction}(?P<amount>{NUMBER})亿元[，,]\s*同比(?P<direction>增长|下降)(?P<growth>{NUMBER})%[。.]"
        matches = list(re.finditer(pattern, body))
        if len(matches) != 1:
            continue
        match = matches[0]
        if re.search(r"预计|预测|估算|将为", body[:match.start()]):
            continue
        value_text = match["amount"] if metric == "amount" else match["growth"] + "%"
        value = float(match["amount"] if metric == "amount" else match["growth"])
        if metric == "growth" and match["direction"] == "下降":
            value = -value
        if float(match["amount"]) < 0 or float(match["growth"]) < 0 or not math.isfinite(value):
            continue
        position = headers[0].end() + substart + match.start()
        quote = match.group()
        proof = {"profile": PROFILE, "text_sha256": page["text_sha256"], "title_quote": title,
                 "publication_quote": re.search(r"20\d{2}年\s*\d{1,2}月\s*\d{1,2}日[^\S\r\n]*来源[：:]国库司", text).group(),
                 "section_quote": headers[0].group(), "subsection_quote": starts[0].group(),
                 "sentence_offsets": [position, position + len(quote)], "metric": metric,
                 "budget_direction": direction, "period_end": period}
        result.append({"request_id": request["id"], "period": period, "value": value, "unit": unit,
                       "definition": request["definition"], "value_text": value_text, "quote": quote,
                       "period_quote": title, "definition_quote": "全国一般公共预算" + direction,
                       "mof_fiscal_proof": proof, "observation_kind": "actual"})
    return result


def reviewed_fiscal_candidates(page, requests):
    try:
        _receipt(page)
        return _candidates(page, requests)
    except (KeyError, TypeError, ValueError, IndexError):
        return []


def verify_fiscal_candidate(candidate, request, page, cutoff, report_month):
    _request(request)
    published = _receipt(page)
    expected = _candidates(page, [request])
    if len(expected) != 1:
        raise ValueError("mof_fiscal_original_sentence_not_unique")
    original = expected[0]
    year, month = map(int, original["period"].split("-"))
    if (published > cutoff or date(year, month, calendar.monthrange(year, month)[1]) > published
            or original["period"] > report_month):
        raise ValueError("mof_fiscal_period_after_publication_or_target")
    expected_metadata = {"series_name": request["series_name"], "receipt_id": page["receipt_id"],
                         "published_at": page["published_at"], "source_url": page["url"],
                         "source_grade": "primary", "publisher_id": "primary:gks.mof.gov.cn"}
    for key in METADATA:
        if key in candidate and candidate[key] != expected_metadata[key]:
            raise ValueError("mof_fiscal_output_provenance_changed")
    content = {key: value for key, value in candidate.items() if key not in METADATA}
    if (isinstance(candidate.get("value"), bool) or content != original
            or json_canonical(content) != json_canonical(original)):
        raise ValueError("mof_fiscal_candidate_not_original")
    proof = original["mof_fiscal_proof"]
    return {"semantic_text": "\n".join((proof["title_quote"], proof["section_quote"],
                                        proof["subsection_quote"], original["quote"])),
            "reviewed_period_and_definition": True, "observation_kind": "actual"}


def json_canonical(value):
    import json
    return json.dumps(value, ensure_ascii=False, sort_keys=True, allow_nan=False)
