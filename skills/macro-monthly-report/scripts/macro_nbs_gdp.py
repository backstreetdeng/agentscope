"""Reviewed national GDP rates and cumulative demand-point reader.

Reads literal official cells/sentences only. Contributions in percent, quarterly
demand points, nominal GDP, deflators and balance/difference derivations are not
substitutes for the five exact reviewed roles below.
"""
import calendar
from datetime import date
from decimal import Decimal
from hashlib import sha256
from html.parser import HTMLParser
import math
import re
from urllib.parse import urlparse

PROFILE = "nbs_gdp_rates_and_cumulative_demand_v1"
PROFILES = {
    "s10-shape7::GDP:不变价:当季同比": ("quarter_gdp_yoy", "%", "GDP当季同比及平减指数：GDP:不变价:当季同比"),
    "s10-shape28::GDP:累计同比": ("cumulative_gdp_yoy", "%", "三大需求对GDP累计增长拉动：GDP:累计同比"),
    "s10-shape28::消费支出拉动": ("cumulative_consumption_points", "百分点", "三大需求对GDP累计增长拉动：消费支出拉动"),
    "s10-shape28::资本形成拉动": ("cumulative_capital_points", "百分点", "三大需求对GDP累计增长拉动：资本形成拉动"),
    "s10-shape28::货物和服务净出口拉动": ("cumulative_net_export_points", "百分点", "三大需求对GDP累计增长拉动：货物和服务净出口拉动"),
}
DEMAND_LABELS = {
    "cumulative_consumption_points": "最终消费支出",
    "cumulative_capital_points": "资本形成总额",
    "cumulative_net_export_points": "货物和服务净出口",
}
QUARTERS = {"一季度": 1, "二季度": 2, "三季度": 3, "四季度": 4}
CUMULATIVE = {"一季度": 1, "上半年": 2, "前三季度": 3, "全年": 4}
NUMBER = r"[+-]?\d+(?:\.\d+)?"
PRICE_NOTE = "绝对额按现价计算，增长速度按不变价计算"
YOY_NOTE = "同比增长速度为与上年同期对比的增长速度"
OUTPUT_METADATA = {"series_name", "receipt_id", "published_at", "source_url", "source_grade", "publisher_id"}


def compact(value):
    return re.sub(r"\s+", "", str(value)).replace("−", "-").replace("％", "%")


def _literal_pattern(value):
    return "".join(re.escape(char) + r"\s*" for char in value)


def _request(request):
    role = PROFILES.get(request.get("id"))
    if (not role or request.get("definition") != role[2] or request.get("unit") != role[1]
            or request.get("frequency") != "quarterly"
            or request.get("chart_id") != request["id"].split("::")[0]
            or request.get("series_name") != request["id"].split("::", 1)[1]
            or "stats.gov.cn" not in request.get("original_publisher_domains", request.get("source_domains", []))):
        raise ValueError("nbs_gdp_request_not_reviewed")
    return role[0]


def _receipt(page):
    url = urlparse(page["url"])
    if (url.scheme != "https" or url.hostname not in {"stats.gov.cn", "www.stats.gov.cn"}
            or url.username or url.password or url.port not in {None, 443}):
        raise ValueError("nbs_gdp_original_publisher_unproven")
    published = date.fromisoformat(page["published_at"])
    if (not page.get("receipt_id") or page.get("truncated")
            or sha256(page["text"].encode()).hexdigest() != page.get("text_sha256")):
        raise ValueError("nbs_gdp_original_receipt_changed")
    # Original publisher URL and a literal date in the release header must agree.
    stamp = re.search(r"/(20\d{4})/t(20\d{6})_\d+\.html$", url.path)
    if not stamp or stamp[2] != published.strftime("%Y%m%d") or stamp[1] != published.strftime("%Y%m"):
        raise ValueError("nbs_gdp_publication_url_date_unproven")
    date_matches = [m for m in re.finditer(r"(20\d{2})[/年.-](\d{1,2})[/月.-](\d{1,2})日?", page["text"][:1000])
                    if tuple(map(int, m.groups())) == (published.year, published.month, published.day)]
    if not date_matches:
        raise ValueError("nbs_gdp_publication_header_date_unproven")
    return published, date_matches[0].group()


class Rows(HTMLParser):
    """Physical cells and spans, not an inferred transposed table."""
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.rows = []; self.spans = []; self.row = None; self.cell = None; self.depth = 0

    def handle_starttag(self, tag, attrs):
        if tag == "table":
            self.depth += 1
            if self.depth != 1: raise ValueError("nbs_gdp_nested_table")
        if tag in {"script", "style", "noscript"}: raise ValueError("nbs_gdp_executable_table")
        if tag == "tr":
            if self.row is not None: raise ValueError("nbs_gdp_nested_row")
            self.row = []; self.rows.append(self.row); self.spans.append([])
        elif tag in {"td", "th"} and self.row is not None:
            if self.cell is not None: raise ValueError("nbs_gdp_nested_cell")
            attrs = dict(attrs); span = []
            for name in ("rowspan", "colspan"):
                value = attrs.get(name, "1")
                if not re.fullmatch(r"\d+", value) or not 1 <= int(value) <= 32:
                    raise ValueError("nbs_gdp_invalid_span")
                span.append(int(value))
            self.spans[-1].append(tuple(span)); self.cell = []

    def handle_endtag(self, tag):
        if tag in {"td", "th"} and self.cell is not None:
            self.row.append("".join(self.cell)); self.cell = None
        elif tag == "tr":
            if self.cell is not None: raise ValueError("nbs_gdp_unclosed_cell")
            self.row = None
        elif tag == "table": self.depth -= 1

    def handle_data(self, text):
        if self.cell is not None: self.cell.append(text)


def _table(page, table):
    raw = table.get("source_html", "")
    if not raw or sha256(raw.encode()).hexdigest() != table.get("html_sha256"):
        raise ValueError("nbs_gdp_original_html_hash_changed")
    parser = Rows(); parser.feed(raw); parser.close()
    if (parser.depth or parser.row is not None or parser.cell is not None
            or len(parser.rows) != len(table["rows"]) or not parser.rows or len(parser.rows) > 100):
        raise ValueError("nbs_gdp_original_rows_changed")
    for index, row in enumerate(table["rows"]):
        cells = [compact(c) for c in parser.rows[index]]
        if (row["row_index"] != index or [compact(c) for c in row["cells"]] != cells
                or compact(row["quote"]) != "|" + "|".join(cells)
                or compact(row["quote"]) not in compact(page["text"])):
            raise ValueError("nbs_gdp_original_cells_or_quote_changed")
    return parser


def _candidate(request, period, token, quote, definition_quote, period_quote, proof):
    if not re.fullmatch(NUMBER, compact(token)):
        return None
    return {"request_id": request["id"], "definition": request["definition"], "period": period,
            "value": float(compact(token)), "value_text": token, "unit": request["unit"],
            "quote": quote, "definition_quote": definition_quote, "period_quote": period_quote,
            "observation_kind": "actual", "nbs_gdp_proof": {"profile": PROFILE, **proof}}


def _table_candidates(page, requests, publication_quote):
    result = []
    if not re.search(r"/(?:sj/zxfb|xxgk/sjfb/zxfb2020)/", urlparse(page["url"]).path):
        return result
    for table in page.get("tables", []):
        try:
            parser = _table(page, table); rows = table["rows"]
            context = table.get("context", "")
            main = re.search(r"(表1\s*(20\d{2})年(一季度|二季度和上半年|三季度和前三季度|四季度和全年|三季度)GDP初步核算数据)\s*$", context)
            historical = re.search(r"(表2\s*GDP同比增长速度)\s*$", context)
            if main:
                caption, year = main[1], int(main[2]); kind = main[3]
                quarterly = kind.split("和")[0]
                q = QUARTERS[quarterly]; period = f"{year}-Q{q}"
                price = re.search(_literal_pattern(PRICE_NOTE), "\n".join(row["quote"] for row in rows))
                if not price: continue
                if [compact(c) for c in rows[0]["cells"]] != ["", "绝对额（亿元）", "比上年同期增长（%）"]: continue
                if q == 1:
                    row_index = 1; role_columns = {"quarter_gdp_yoy": 2, "cumulative_gdp_yoy": 2}
                    if parser.spans[0] != [(1, 1)] * 3: continue
                else:
                    cumulative = {2: "上半年", 3: "前三季度", 4: "全年"}[q]
                    if "和" not in kind: continue
                    if (parser.spans[0] != [(2, 1), (1, 2), (1, 2)]
                            or [compact(c) for c in rows[1]["cells"]] != [quarterly, cumulative, quarterly, cumulative]
                            or parser.spans[1] != [(1, 1)] * 4): continue
                    row_index = 2; role_columns = {"quarter_gdp_yoy": 3, "cumulative_gdp_yoy": 4}
                row = rows[row_index]
                if compact(row["cells"][0]) != "GDP" or parser.spans[row_index] != [(1, 1)] * len(row["cells"]): continue
                for request in requests:
                    try: role = _request(request)
                    except (ValueError, KeyError, TypeError): continue
                    if role not in role_columns: continue
                    column = role_columns[role]
                    proof = {"mode": "gdp_main_table", "role": role, "receipt_text_sha256": page["text_sha256"],
                             "table_index": table["table_index"], "row_index": row_index, "column_index": column,
                             "table_html_sha256": table["html_sha256"], "caption_quote": caption,
                             "header_quotes": [r["quote"] for r in rows[:row_index]], "price_note_quote": price.group(),
                             "publication_quote": publication_quote}
                    candidate = _candidate(request, period, row["cells"][column], row["quote"], "GDP", caption, proof)
                    if candidate: result.append(candidate)
            elif historical:
                caption = historical[1]
                price = re.search(_literal_pattern(PRICE_NOTE), context)
                if not price or compact(price.group()) not in compact(page["text"]): continue
                if ([compact(c) for c in rows[0]["cells"]] != ["单位：%"] or parser.spans[0] != [(1, 5)]
                        or [compact(c) for c in rows[1]["cells"]] != ["年份", "1季度", "2季度", "3季度", "4季度"]
                        or parser.spans[1] != [(1, 1)] * 5): continue
                note = re.search(_literal_pattern(YOY_NOTE), "\n".join(row["quote"] for row in rows))
                if not note: continue
                values = []
                for row in rows[2:]:
                    if (len(row["cells"]) != 5 or parser.spans[row["row_index"]] != [(1, 1)] * 5
                            or not re.fullmatch(r"20\d{2}", compact(row["cells"][0]))): continue
                    year = int(compact(row["cells"][0]))
                    for column in range(1, 5):
                        if re.fullmatch(NUMBER, compact(row["cells"][column])):
                            values.append((f"{year}-Q{column}", row, column))
                for request in requests:
                    try: role = _request(request)
                    except (ValueError, KeyError, TypeError): continue
                    if role != "quarter_gdp_yoy": continue
                    # One coherent publisher vintage and the reviewed four-quarter history.
                    for period, row, column in sorted(values, key=lambda x: x[0])[-max(4, int(request.get("history_count", 4))):]:
                        proof = {"mode": "gdp_quarter_history_table", "role": role,
                                 "receipt_text_sha256": page["text_sha256"], "table_index": table["table_index"],
                                 "row_index": row["row_index"], "column_index": column,
                                 "table_html_sha256": table["html_sha256"], "caption_quote": caption,
                                 "header_quotes": [rows[0]["quote"], rows[1]["quote"]],
                                 "price_note_quote": price.group(), "yoy_note_quote": note.group(),
                                 "publication_quote": publication_quote}
                        candidate = _candidate(request, period, row["cells"][column], row["quote"], "GDP", caption, proof)
                        if candidate: result.append(candidate)
        except (ValueError, KeyError, TypeError, IndexError):
            continue
    return result


def _unique(matches):
    # Publisher pages may carry an identical accessibility/print copy.
    values = {m.group(): m for m in matches}
    return next(iter(values.values())) if len(values) == 1 else None


def _actual_matches(pattern, text, year):
    """Bind qualifiers preceding the literal, not just the captured number."""
    for match in re.finditer(pattern, text):
        start = max(text.rfind("。", 0, match.start()), text.rfind("\n", 0, match.start()), text.rfind("；", 0, match.start())) + 1
        prefix = text[start:match.start()]
        if re.search(r"预计|预测|估算|目标|将|去年|上年|前年", prefix): continue
        years = re.findall(r"(20\d{2})年", prefix)
        if years and int(years[-1]) != year: continue
        yield match


def _prose_candidates(page, requests, published, publication_quote):
    path = urlparse(page["url"]).path; text = page["text"]
    quarterly = re.search(r"/(?:sj/(?:sjjd|zxfbhjd)|xxgk/jd/sjjd2020)/", path)
    annual = re.search(r"/xxgk/sjfb/tjgb2020/", path)
    if not quarterly and not annual: return []
    annual_title = re.search(r"中华人民共和国(20\d{2})年国民经济和社会发展统计公报", text[:1000]) if annual else None
    if annual:
        if not annual_title or published.year != int(annual_title[1]) + 1 or published.month not in {1, 2, 3}: return []
        year, marker = int(annual_title[1]), "全年"
        price = re.search(r"\[2\]国内生产总值[^\n。]*增长速度按不变价格计算", text)
        if not price: return []
        gdp = _unique(_actual_matches(rf"初步核算[，,]全年国内生产总值\[2\]({NUMBER})亿元[，,]比上年增长({NUMBER})%", text, year))
        if not gdp: return []
        # The three direct points belong to the same annual GDP paragraph.
        paragraph = text[gdp.start():text.find("\n", gdp.start()) if "\n" in text[gdp.start():] else len(text)]
        block = paragraph.split("分季度看", 1)[0]
        year_quote = annual_title.group(); gdp_number = gdp[2]
        point_pattern = lambda label: rf"{label}拉动国内生产总值增长({NUMBER})个百分点"
    else:
        marker = {4: "一季度", 7: "上半年", 10: "前三季度"}.get(published.month)
        if not marker: return []
        year = published.year
        title_years = re.findall(rf"(20\d{{2}})年{marker}", text.splitlines()[0])
        if any(int(value) != year for value in title_years): return []
        gdp = _unique(_actual_matches(rf"{marker}[，,](?:我国)?(?:国内生产总值[（(]GDP[）)]|GDP)为({NUMBER})亿元[，,]按不变价格计算[，,]同比增长({NUMBER})%", text, year))
        if not gdp: return []
        price = re.search("按不变价格计算", gdp.group())
        block = text; year_quote = publication_quote; gdp_number = gdp[2]
        point_pattern = lambda label: rf"{marker}[，,]{label}(?:对经济增长贡献率为{NUMBER}%[，,])?拉动GDP增长({NUMBER})个百分点"
    period = f"{year}-Q{CUMULATIVE[marker]}"
    points = {role: _unique(_actual_matches(point_pattern(label), block, year)) for role, label in DEMAND_LABELS.items()}
    complete = all(points.values())
    identity = []
    if complete:
        identity = [{"role": role, "quote": found.group(), "value": float(found[1])} for role, found in points.items()]
        if abs(sum(Decimal(str(item["value"])) for item in identity) - Decimal(gdp_number)) > Decimal("0.2"):
            raise ValueError("nbs_gdp_cumulative_demand_identity_mismatch")
    result = []
    for request in requests:
        try: role = _request(request)
        except (ValueError, KeyError, TypeError): continue
        if role == "cumulative_gdp_yoy":
            found, token, definition = gdp, gdp_number, "国内生产总值" if "国内生产总值" in gdp.group() else "GDP"
        elif role in DEMAND_LABELS and complete:
            found, token, definition = points[role], points[role][1], DEMAND_LABELS[role]
        else: continue
        quote = found.group()
        if re.search(r"预计|预测|估算|目标|将", quote): continue
        proof = {"mode": "gdp_cumulative_prose", "role": role, "receipt_text_sha256": page["text_sha256"],
                 "period_marker_quote": marker, "year_binding_quote": year_quote,
                 "year_binding_rule": "explicit_annual_title" if annual else "official_quarter_next_month_release",
                 "publication_quote": publication_quote, "price_note_quote": price.group(),
                 "cumulative_gdp_quote": gdp.group(), "cumulative_gdp_value": float(gdp_number),
                 "cumulative_demand_identity": identity}
        candidate = _candidate(request, period, token, quote, definition, marker, proof)
        if candidate: result.append(candidate)
    return result


def reviewed_gdp_candidates(page, requests):
    """Unsupported public documents yield no match, not invented candidates."""
    try:
        published, publication_quote = _receipt(page)
        candidates = _table_candidates(page, requests, publication_quote) + _prose_candidates(page, requests, published, publication_quote)
        grouped = {}
        for item in candidates:
            grouped.setdefault((item["request_id"], item["period"]), []).append(item)
        return [items[0] for items in grouped.values() if len({item["value"] for item in items}) == 1]
    except (ValueError, KeyError, TypeError, AttributeError, IndexError):
        return []


def verify_gdp_candidate(candidate, request, page, cutoff, report_month):
    """Rebind the exact role, original fields, dates and proof on every replay."""
    _request(request); published, _ = _receipt(page)
    cutoff = cutoff if isinstance(cutoff, date) else date.fromisoformat(str(cutoff))
    if published > cutoff: raise ValueError("nbs_gdp_publication_after_cutoff")
    period = candidate.get("period", "")
    if not re.fullmatch(r"20\d{2}-Q[1-4]", period): raise ValueError("nbs_gdp_period_invalid")
    year, quarter = int(period[:4]), int(period[-1]); month = quarter * 3
    observed_end = date(year, month, calendar.monthrange(year, month)[1])
    if observed_end > published or f"{year}-{month:02d}" > report_month:
        raise ValueError("nbs_gdp_period_after_publication_or_target")
    value = candidate.get("value")
    if type(value) not in {int, float} or not math.isfinite(value): raise ValueError("nbs_gdp_value_invalid")
    expected_metadata = {"series_name": request["series_name"], "receipt_id": page["receipt_id"],
                         "published_at": page["published_at"], "source_url": page["url"],
                         "source_grade": "primary", "publisher_id": "primary:" + urlparse(page["url"]).hostname}
    for key in OUTPUT_METADATA:
        if key in candidate and candidate[key] != expected_metadata[key]: raise ValueError("nbs_gdp_output_provenance_changed")
    clean = {key: value for key, value in candidate.items() if key not in OUTPUT_METADATA}
    proof = clean.get("nbs_gdp_proof")
    if not isinstance(proof, dict): raise ValueError("nbs_gdp_proof_invalid")
    for key in ("table_index", "row_index", "column_index"):
        if key in proof and (type(proof[key]) is not int or proof[key] < 0): raise ValueError("nbs_gdp_coordinates_invalid")
    for item in proof.get("cumulative_demand_identity", []):
        if type(item.get("value")) not in {int, float} or not math.isfinite(item["value"]): raise ValueError("nbs_gdp_identity_value_invalid")
    if "cumulative_gdp_value" in proof and type(proof["cumulative_gdp_value"]) not in {int, float}:
        raise ValueError("nbs_gdp_identity_value_invalid")
    originals = reviewed_gdp_candidates(page, [request])
    if clean not in originals: raise ValueError("nbs_gdp_candidate_not_original")
    proof = clean["nbs_gdp_proof"]
    semantic = [clean["quote"], clean["definition_quote"], clean["period_quote"]]
    semantic.extend(proof.get(key, "") for key in ("caption_quote", "price_note_quote", "yoy_note_quote", "publication_quote", "year_binding_quote", "cumulative_gdp_quote"))
    semantic.extend(proof.get("header_quotes", []))
    semantic.extend(item["quote"] for item in proof.get("cumulative_demand_identity", []))
    if any(piece and compact(piece) not in compact(page["text"]) for piece in semantic): raise ValueError("nbs_gdp_semantics_not_original")
    return {"semantic_text": "\n".join(piece for piece in semantic if piece), "reviewed_period_and_definition": True,
            "observation_kind": "actual", "nbs_gdp_proof": proof}
