"""Replay original NBS grouped PMI levels and new-home tier price changes.

Only the reviewed current-month manufacturing paragraph and new-home paragraphs
are read. Group labels and their ordered numbers are rebound on every replay;
nonmanufacturing, second-hand homes and previous-month transition values cannot
substitute for the requested series. No network or model is used here.
"""
import calendar
from datetime import date
from hashlib import sha256
import math
import re
from urllib.parse import urlparse

PMI_PROFILE = "nbs_pmi_grouped_prose_v1"
HOUSING_PROFILE = "nbs_new_home_tier_price_v1"
ORIENTATION = "official_nbs_current_month_grouped_prose"
NUMBER = r"\d+(?:\.\d+)?"
PMI_COMPONENTS = {
    0: ("生产", "生产指数"), 1: ("新订单", "新订单指数"),
    8: ("原材料库存", "原材料库存指数"), 9: ("从业人员", "从业人员指数"),
    10: ("供货商配送时间", "供应商配送时间指数"),
}
TIERS = {"一线城市", "二线城市", "三线城市"}
METADATA = {"series_name", "receipt_id", "source_url", "source_grade", "publisher_id"}


def _compact(value):
    return re.sub(r"\s+", "", str(value))


def _request(request):
    cid, name = request.get("chart_id"), request.get("series_name")
    if (request.get("frequency") != "monthly" or "stats.gov.cn" not in
            request.get("original_publisher_domains", request.get("source_domains", []))):
        raise ValueError("nbs_grouped_request_not_reviewed")
    if cid == "s11-shape12":
        aliases = ({"制造业采购经理指数", "制造业PMI", "PMI"} if name == "PMI" else
                   {name.split(":", 1)[1]} if name in {"PMI:大型企业", "PMI:中型企业", "PMI:小型企业"} else None)
        if (aliases is None or request.get("id") != cid + "::" + name or request.get("unit") != "指数"
                or request.get("definition") != "制造业PMI企业规模：" + name
                or set(request.get("definition_aliases", [])) != aliases):
            raise ValueError("nbs_grouped_request_not_reviewed")
        return PMI_PROFILE, "PMI" if name == "PMI" else name.split(":", 1)[1], "level"
    if cid == "s11-shape15":
        index = request.get("category_index")
        if type(index) is not int or index not in PMI_COMPONENTS:
            raise ValueError("nbs_grouped_request_not_reviewed")
        label, original = PMI_COMPONENTS[index]
        if (request.get("id") != cid + "::category" + str(index) or name != "snapshot"
                or request.get("definition") != "PMI分项指数：" + label or request.get("unit") != "指数"
                or set(request.get("definition_aliases", [])) != {label, label + "指数"}):
            raise ValueError("nbs_grouped_request_not_reviewed")
        return PMI_PROFILE, original, "level"
    if cid in {"s18-shape17", "s18-shape21"}:
        metric = "环比" if cid == "s18-shape17" else "同比"
        if (name not in TIERS or request.get("id") != cid + "::" + name
                or request.get("definition") != "70城新房" + metric + "：" + name
                or request.get("unit") != "%" or set(request.get("definition_aliases", [])) != {name}):
            raise ValueError("nbs_grouped_request_not_reviewed")
        return HOUSING_PROFILE, name, metric
    raise ValueError("nbs_grouped_request_not_reviewed")


def _receipt(page, cutoff_date=None):
    parsed = urlparse(page["url"])
    if (parsed.scheme != "https" or parsed.hostname not in {"stats.gov.cn", "www.stats.gov.cn"}
            or parsed.username is not None or parsed.password is not None or parsed.port not in {None, 443}
            or not re.fullmatch(r"/(?:sj/(?:zxfb|zxfbhjd|sjjd)|xxgk/(?:sjfb/zxfb2020|jd/sjjd2020))/\d{6}/t20\d{6}_\d+\.html", parsed.path)):
        raise ValueError("nbs_grouped_original_release_publisher_unproven")
    text = page.get("text", "")
    if (not isinstance(text, str) or not text or not page.get("receipt_id") or page.get("truncated")
            or sha256(text.encode()).hexdigest() != page.get("text_sha256")):
        raise ValueError("nbs_grouped_original_text_hash_changed")
    published = date.fromisoformat(page["published_at"])
    if cutoff_date and published > _date(cutoff_date):
        raise ValueError("nbs_grouped_publication_after_cutoff")
    return text, published


def _date(value):
    return value if isinstance(value, date) else date.fromisoformat(str(value))


def _publication(text, before, published):
    # Only literal release-header timestamps/成文日期 before the article body.
    matches = []
    for found in re.finditer(r"(?<!\d)(20\d{2})[/年.-](\d{1,2})[/月.-](\d{1,2})日?", text[:before]):
        try:
            if date(*(int(v) for v in found.groups())) == published:
                matches.append(found)
        except ValueError:
            continue
    if not matches:
        raise ValueError("nbs_grouped_literal_publication_header_missing")
    return matches[0]


def _span(match, group=0, offset=0):
    return [offset + match.start(group), offset + match.end(group)]


def _pmi_context(text, published):
    starts = list(re.finditer(r"一、中国制造业采购经理指数运行情况", text))
    contexts = []
    for start in starts:
        end = re.search(r"表1\s*中国制造业PMI及构成指数[（(]经季节调整[）)]", text[start.end():])
        if not end:
            continue
        stop = start.end() + end.start()
        contexts.append((start, stop, text[start.end():stop]))
    if not contexts or len({_compact(v[2]) for v in contexts}) != 1:
        raise ValueError("nbs_grouped_manufacturing_body_ambiguous")
    start, stop, body = contexts[0]
    period = re.search(r"(?P<month>\d{1,2})月份[，,]制造业采购经理指数[（(]PMI[）)]为", body)
    if not period or int(period["month"]) != published.month:
        raise ValueError("nbs_grouped_current_month_release_unproven")
    publication = _publication(text, start.start(), published)
    title = list(re.finditer(r"(?P<year>20\d{2})年(?P<month>\d{1,2})月中国采购经理指数运行情况", text[:start.start()]))
    if title and any((int(m["year"]), int(m["month"])) != (published.year, published.month) for m in title):
        raise ValueError("nbs_grouped_pmi_title_period_disagrees")
    # The information-disclosure mirror omits the title but retains its official
    # 成文日期. This reviewed current-month release requires the source producer,
    # manufacturing section and literal body month to agree with that header.
    if not title and not re.search(r"成文日期\s*" + re.escape(publication.group()), text[:start.start()]):
        raise ValueError("nbs_grouped_pmi_release_year_unproven")
    if "国家统计局服务业调查中心" not in text[:start.start()] or "中国物流与采购联合会" not in text[:start.start()]:
        raise ValueError("nbs_grouped_pmi_producer_missing")
    proof = {"section_quote": start.group(), "section_offsets": _span(start),
             "body_offsets": [start.end(), stop], "publication_quote": publication.group(),
             "publication_offsets": _span(publication), "period_quote": period.group(),
             "period_offsets": _span(period, offset=start.end()),
             "year_binding_rule": "explicit_article_title" if title else "official_same_month_release_header",
             "year_binding_quote": title[-1].group() if title else publication.group(),
             "year_binding_offsets": _span(title[-1]) if title else _span(publication)}
    return f"{published.year}-{published.month:02d}", body, start.end(), proof


def _pmi_matches(body, label):
    if label == "PMI":
        pattern = rf"\d{{1,2}}月份[，,](?P<label>制造业采购经理指数[（(]PMI[）)])为(?P<value>{NUMBER})(?P<unit>[%％])[^。]*。"
    elif label.endswith("企业"):
        size = label[0]
        matches = []
        for found in re.finditer(rf"(?P<label>[大中小]型企业PMI)为(?P<value>{NUMBER})(?P<unit>[%％])", body):
            if found["label"].startswith(size):
                matches.append((found, "value", [label], 0, "PMI"))
        for names in ("大、中、小", "大、中", "大、小", "中、小"):
            order = [part + "型企业" for part in names.split("、")]
            if label not in order:
                continue
            values = rf"(?P<v0>{NUMBER})(?P<u0>[%％])"
            for i in range(1, len(order)):
                values += (r"和" if i == len(order) - 1 else r"、") + rf"(?P<v{i}>{NUMBER})(?P<u{i}>[%％])"
            pattern = rf"(?P<label>{names}型企业PMI)分别为" + values
            matches += [(m, "v" + str(order.index(label)), order, order.index(label), "PMI") for m in re.finditer(pattern, body)]
        return matches
    else:
        pattern = rf"(?P<label>{re.escape(label)})为(?P<value>{NUMBER})(?P<unit>[%％])[^。]*。"
    return [(m, "value", [label], 0, m["label"]) for m in re.finditer(pattern, body)]


def _actual_pmi_match(body, found):
    start = max(body.rfind("。", 0, found.start()), body.rfind("\n", 0, found.start()),
                body.rfind("；", 0, found.start())) + 1
    return not re.search(r"预计|预测|估算|目标|将|去年|上年|累计", body[start:found.start()])


def _housing_context(text, published, metric):
    titles = list(re.finditer(r"解读(?P<year>20\d{2})年(?P<month>\d{1,2})月份商品住宅销售价格变动情况统计数据", text))
    if len(titles) != 1:
        raise ValueError("nbs_grouped_housing_article_period_ambiguous")
    title = titles[0]; year, month = int(title["year"]), int(title["month"])
    if not 1 <= month <= 12:
        raise ValueError("nbs_grouped_housing_month_invalid")
    publication = _publication(text, title.start(), published)
    summaries = list(re.finditer(r"(?P<year>20\d{2})年(?P<month>\d{1,2})月份[，,]70个大中城市中", text[title.end():]))
    if len(summaries) != 1 or (int(summaries[0]["year"]), int(summaries[0]["month"])) != (year, month):
        raise ValueError("nbs_grouped_housing_title_and_body_period_disagree")
    period = f"{year}-{month:02d}"
    if date(year, month, calendar.monthrange(year, month)[1]) > published:
        raise ValueError("nbs_grouped_housing_month_not_finished")
    pattern = rf"(?P<marker>{month}月份)[，,]一线城市新建商品住宅销售价格{metric}[^\r\n]+"
    matches = list(re.finditer(pattern, text[title.end():]))
    if len(matches) != 1:
        raise ValueError("nbs_grouped_housing_current_new_home_paragraph_ambiguous")
    found = matches[0]; offset = title.end(); body = found.group()
    if "二手住宅" in body or re.search(r"预计|预测|目标|将", body):
        raise ValueError("nbs_grouped_housing_actual_new_home_unproven")
    notes = list(re.finditer(r"70个大中城市房地产价格统计一二三线城市划分[：:][^\r\n]+", text))
    if len(notes) != 1 or not all(v in notes[0].group() for v in ("一线城市指", "二线城市指", "三线城市指")):
        raise ValueError("nbs_grouped_seventy_city_tier_scope_missing")
    proof = {"section_quote": metric, "section_offsets": _span(found, offset=offset),
             "body_offsets": _span(found, offset=offset), "publication_quote": publication.group(),
             "publication_offsets": _span(publication), "period_quote": title.group(),
             "period_offsets": _span(title), "year_binding_rule": "explicit_article_title",
             "year_binding_quote": title.group(), "year_binding_offsets": _span(title),
             "scope_quote": notes[0].group(), "scope_offsets": _span(notes[0])}
    proof["current_month_summary_quote"] = summaries[0].group()
    proof["current_month_summary_offsets"] = _span(summaries[0], offset=title.end())
    return period, body, offset + found.start(), proof


def _housing_matches(body, label, metric):
    result = []
    # The current rate follows 转为; the previous month's preceding rate is not
    # a second candidate. Explicit 持平 is a literal qualitative zero.
    previous = rf"(?:由上月(?:(?:上涨|下降){NUMBER}[%％]|持平)转为)?"
    current = rf"(?:(?P<direction>上涨|下降)(?P<value>{NUMBER})(?P<unit>[%％])|(?P<zero>持平))"
    pattern = rf"(?P<label>{label})新建商品住宅销售价格{metric}" + previous + current
    for found in re.finditer(pattern, body):
        result.append((found, "value", [label], 0, found["label"], found["direction"] or "持平"))
    names = "二、三线城市"
    if label in {"二线城市", "三线城市"}:
        pattern = (rf"(?P<label>{names})新建商品住宅销售价格{metric}分别(?P<direction>上涨|下降)"
                   rf"(?P<v0>{NUMBER})(?P<u0>[%％])和(?P<v1>{NUMBER})(?P<u1>[%％])")
        order = ["二线城市", "三线城市"]
        for found in re.finditer(pattern, body):
            result.append((found, "v" + str(order.index(label)), order, order.index(label), found["label"], found["direction"]))
    return result


def _candidate(page, request, text, published, cutoff_date=None, report_month=None):
    profile, label, metric = _request(request)
    if profile == PMI_PROFILE:
        period, body, offset, context = _pmi_context(text, published)
        matches = [item for item in _pmi_matches(body, label) if _actual_pmi_match(body, item[0])]
    else:
        period, body, offset, context = _housing_context(text, published, metric)
        matches = _housing_matches(body, label, metric)
    if report_month and period > str(report_month):
        raise ValueError("nbs_grouped_actual_month_after_target")
    if len(matches) != 1:
        raise ValueError("nbs_grouped_current_metric_not_unique")
    match, field, order, index, definition_quote, *directions = matches[0]
    direction = directions[0] if directions else "level"
    zero = direction == "持平"
    token = "0" if zero else match[field]
    value = float(token) * (-1 if direction == "下降" else 1)
    if not math.isfinite(value) or (profile == PMI_PROFILE and not 0 <= value <= 100):
        raise ValueError("nbs_grouped_original_value_invalid")
    unit_field = "u" + field[1:] if field.startswith("v") and field != "value" else "unit"
    proof = {"profile": profile, "orientation": ORIENTATION, "text_sha256": page["text_sha256"],
             "source_label": label, "metric": metric, "group_order": order, "member_index": index,
             "sentence_offsets": _span(match, offset=offset), "direction": direction,
             "value_binding_rule": "explicit_unchanged_zero" if zero else "ordered_literal_number",
             "value_offsets": _span(match, "zero" if zero else field, offset),
             "unit_quote": "" if zero else match[unit_field],
             "unit_offsets": None if zero else _span(match, unit_field, offset), **context}
    return {"request_id": request["id"], "definition": request["definition"], "period": period,
            "value": value, "value_text": token, "unit": request["unit"], "quote": match.group(),
            "definition_quote": definition_quote, "period_quote": context["period_quote"],
            "published_at": page["published_at"], "observation_kind": "actual",
            "nbs_grouped_prose_proof": proof}


def reviewed_grouped_prose_candidates(page, requests, cutoff_date=None, report_month=None):
    try:
        text, published = _receipt(page, cutoff_date)
    except (ValueError, KeyError, TypeError):
        return []
    result = []
    for request in requests:
        try:
            result.append(_candidate(page, request, text, published, cutoff_date, report_month))
        except (ValueError, KeyError, TypeError, IndexError):
            continue
    return result


def verify_grouped_prose_candidate(candidate, request, page, cutoff_date=None, report_month=None):
    text, published = _receipt(page, cutoff_date)
    expected = _candidate(page, request, text, published, cutoff_date, report_month)
    value = candidate.get("value")
    if type(value) not in {int, float} or not math.isfinite(value):
        raise ValueError("nbs_grouped_candidate_numeric_invalid")
    metadata = {"series_name": request["series_name"], "receipt_id": page["receipt_id"],
                "source_url": page["url"], "source_grade": "primary", "publisher_id": "primary:" + urlparse(page["url"]).hostname}
    for key in METADATA:
        if key in candidate and candidate[key] != metadata[key]:
            raise ValueError("nbs_grouped_output_provenance_changed")
    content = {key: value for key, value in candidate.items() if key not in METADATA}
    # Canonical comparison catches bool/int offsets and all candidate-supplied
    # order, labels, date, sign, units and arbitrary proof fields.
    import json
    if json.dumps(content, sort_keys=True, ensure_ascii=False, allow_nan=False) != json.dumps(expected, sort_keys=True, ensure_ascii=False, allow_nan=False):
        raise ValueError("nbs_grouped_candidate_not_original_current_month")
    proof = expected["nbs_grouped_prose_proof"]
    return {"semantic_text": "\n".join((proof["year_binding_quote"], proof["publication_quote"],
                                        proof["section_quote"], expected["quote"], proof.get("scope_quote", ""))),
            "reviewed_period_and_definition": True, "observation_kind": "actual",
            "explicit_unchanged_zero_verified": proof["value_binding_rule"] == "explicit_unchanged_zero"}
