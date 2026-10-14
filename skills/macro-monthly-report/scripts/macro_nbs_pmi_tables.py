"""Exact NBS manufacturing PMI tables with independently expanded headers.

The physical table1 has a two-level merged header after its unit row. Table2
has eight other indicators; neither layout is a flat generic category table.
Only original seasonally adjusted monthly index levels are accepted.
"""
from datetime import date
from hashlib import sha256
from html.parser import HTMLParser
import json
import math
import re
from urllib.parse import urlparse

ORIENTATION = "official_nbs_pmi_rows"
PROFILES = {1: "nbs_manufacturing_pmi_main_v1", 2: "nbs_manufacturing_pmi_other_v1"}
TABLE_LABELS = {
    1: ["", "PMI", "生产", "新订单", "原材料库存", "从业人员", "供应商配送时间"],
    2: ["", "新出口订单", "进口", "采购量", "主要原材料购进价格", "出厂价格", "产成品库存", "在手订单", "生产经营活动预期"],
}
CATEGORIES = {
    0: ("生产", 1, "生产"), 1: ("新订单", 1, "新订单"),
    2: ("新出口订单", 2, "新出口订单"), 3: ("在手订单", 2, "在手订单"),
    4: ("产成品库存", 2, "产成品库存"), 5: ("采购量", 2, "采购量"),
    6: ("进口", 2, "进口"), 7: ("主要原材料购进价格", 2, "主要原材料购进价格"),
    8: ("原材料库存", 1, "原材料库存"), 9: ("从业人员", 1, "从业人员"),
    10: ("供货商配送时间", 1, "供应商配送时间"), 11: ("生产经营活动预期", 2, "生产经营活动预期"),
}
METADATA = {"series_name", "receipt_id", "source_url", "source_grade", "publisher_id", "published_at", "observation_kind"}


def compact(value):
    return re.sub(r"\s+", "", str(value)).replace("％", "%")


class Rows(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.rows = []; self.spans = []; self.row = None; self.cell = None; self.depth = 0

    def handle_starttag(self, tag, attrs):
        if tag == "table":
            self.depth += 1
            if self.depth != 1: raise ValueError("nbs_pmi_nested_table")
        if tag in {"script", "style", "noscript"}: raise ValueError("nbs_pmi_executable_table")
        if tag == "tr":
            if self.row is not None: raise ValueError("nbs_pmi_nested_rows")
            self.row = []; self.rows.append(self.row); self.spans.append([])
        elif tag in {"td", "th"} and self.row is not None:
            if self.cell is not None: raise ValueError("nbs_pmi_nested_cell")
            attrs = dict(attrs); spans = []
            for key in ("rowspan", "colspan"):
                token = attrs.get(key, "1")
                if not re.fullmatch(r"\d+", token) or not 1 <= int(token) <= 32:
                    raise ValueError("nbs_pmi_invalid_span")
                spans.append(int(token))
            self.spans[-1].append(tuple(spans)); self.cell = []

    def handle_endtag(self, tag):
        if tag in {"td", "th"} and self.cell is not None:
            self.row.append("".join(self.cell)); self.cell = None
        elif tag == "tr":
            if self.cell is not None: raise ValueError("nbs_pmi_unclosed_cell")
            self.row = None
        elif tag == "table": self.depth -= 1

    def handle_data(self, text):
        if self.cell is not None: self.cell.append(text)


def _expanded(parser, header_count, width):
    """Each logical header slot points to its ORIGINAL physical cell."""
    grid = {}
    for ri in range(header_count):
        col = 0
        for ci, value in enumerate(parser.rows[ri]):
            while (ri, col) in grid: col += 1
            rowspan, colspan = parser.spans[ri][ci]
            if ri + rowspan > header_count or col + colspan > width:
                raise ValueError("nbs_pmi_header_span_outside_reviewed_grid")
            for row in range(ri, ri + rowspan):
                for column in range(col, col + colspan):
                    if (row, column) in grid: raise ValueError("nbs_pmi_header_overlap")
                    grid[row, column] = (compact(value), ri, ci)
            col += colspan
    if set(grid) != {(r, c) for r in range(header_count) for c in range(width)}:
        raise ValueError("nbs_pmi_header_grid_incomplete")
    return grid


def _receipt(page, cutoff_date=None):
    parsed = urlparse(page["url"])
    if (parsed.scheme != "https" or parsed.hostname not in {"stats.gov.cn", "www.stats.gov.cn"}
            or parsed.username is not None or parsed.password is not None or parsed.port not in {None, 443}
            or not re.fullmatch(r"/(?:sj/(?:zxfb|zxfbhjd)|xxgk/sjfb/zxfb2020)/\d{6}/t20\d{6}_\d+\.html", parsed.path)):
        raise ValueError("nbs_pmi_original_release_publisher_unproven")
    text = page.get("text", "")
    if (not isinstance(text, str) or not text or not page.get("receipt_id") or page.get("truncated")
            or sha256(text.encode()).hexdigest() != page.get("text_sha256")):
        raise ValueError("nbs_pmi_original_text_changed")
    published = date.fromisoformat(page["published_at"])
    dates = []
    for match in re.finditer(r"(?<!\d)(20\d{2})[/年.-](\d{1,2})[/月.-](\d{1,2})日?", text[:1000]):
        try:
            if date(*(int(v) for v in match.groups())) == published: dates.append(match.group())
        except ValueError: continue
    if not dates: raise ValueError("nbs_pmi_literal_publication_header_missing")
    if cutoff_date and published > _date(cutoff_date): raise ValueError("nbs_pmi_publication_after_cutoff")
    return published, dates[0]


def _date(value):
    return value if isinstance(value, date) else date.fromisoformat(str(value))


def _table(page, table):
    raw = table.get("source_html", "")
    if not raw or sha256(raw.encode()).hexdigest() != table.get("html_sha256"):
        raise ValueError("nbs_pmi_original_html_hash_changed")
    parser = Rows(); parser.feed(raw); parser.close()
    rows = table["rows"]
    if (parser.depth or parser.row is not None or parser.cell is not None or not parser.rows
            or len(rows) != len(parser.rows) or not 3 <= len(rows) <= 30):
        raise ValueError("nbs_pmi_original_rows_changed")
    for ri, row in enumerate(rows):
        expected = [compact(v) for v in parser.rows[ri]]
        if (type(row.get("row_index")) is not int or row["row_index"] != ri
                or [compact(v) for v in row["cells"]] != expected
                or compact(row.get("quote", "")) != "|" + "|".join(expected)
                or compact(row["quote"]) not in compact(page["text"])):
            raise ValueError("nbs_pmi_original_cell_or_row_quote_changed")
    caption = re.search(r"(表(?P<number>[12])\s*中国制造业PMI(?P<kind>及构成指数|其他相关指标情况)[（(]经季节调整[）)])\s*$", table.get("context", ""))
    if not caption or compact(caption[1]) not in compact(page["text"]):
        raise ValueError("nbs_pmi_exact_manufacturing_caption_missing")
    number = int(caption["number"])
    if caption["kind"] != {1:"及构成指数",2:"其他相关指标情况"}[number]:
        raise ValueError("nbs_pmi_caption_table_kind_disagrees")
    width = len(TABLE_LABELS[number]); count = 3 if number == 1 else 2
    if compact(rows[0]["cells"][0]) != "单位:%".replace(":", "：") or len(rows[0]["cells"]) != 1 or parser.spans[0] != [(1, width)]:
        raise ValueError("nbs_pmi_original_percent_header_unproven")
    grid = _expanded(parser, count, width)
    if [grid[count - 1, col][0] for col in range(width)] != TABLE_LABELS[number]:
        raise ValueError("nbs_pmi_expanded_indicator_header_changed")
    if number == 1:
        if (parser.spans[1] != [(2, 1), (2, 1), (1, 5)] or [compact(v) for v in rows[1]["cells"]] != ["", "PMI", ""]
                or parser.spans[2] != [(1, 1)] * 5):
            raise ValueError("nbs_pmi_reviewed_header_hierarchy_changed")
    elif parser.spans[1] != [(1, 1)] * width:
        raise ValueError("nbs_pmi_other_header_spans_changed")
    periods = []
    for ri in range(count, len(rows)):
        row = rows[ri]
        if len(row["cells"]) != width or parser.spans[ri] != [(1, 1)] * width:
            raise ValueError("nbs_pmi_data_row_physical_width_changed")
        marker = re.fullmatch(r"(20\d{2})年(\d{1,2})月", compact(row["cells"][0]))
        if not marker or not 1 <= int(marker[2]) <= 12:
            raise ValueError("nbs_pmi_original_month_row_missing")
        period = f"{int(marker[1])}-{int(marker[2]):02d}"
        if period in periods: raise ValueError("nbs_pmi_month_row_duplicated")
        periods.append(period)
    if periods != sorted(periods): raise ValueError("nbs_pmi_month_rows_not_ascending")
    return number, count, caption[1], parser, grid, periods


def _request(request):
    if (request.get("unit") != "指数" or request.get("frequency") != "monthly" or "stats.gov.cn" not in
            request.get("original_publisher_domains", request.get("source_domains", []))):
        raise ValueError("nbs_pmi_request_not_reviewed")
    if request.get("id") == "s11-shape12::PMI":
        if (request.get("chart_id") != "s11-shape12" or request.get("series_name") != "PMI"
                or request.get("definition") != "制造业PMI企业规模：PMI"
                or set(request.get("definition_aliases", [])) != {"制造业采购经理指数", "制造业PMI", "PMI"}):
            raise ValueError("nbs_pmi_request_not_reviewed")
        return 1, "PMI"
    index = request.get("category_index")
    if type(index) is not int or index not in CATEGORIES:
        raise ValueError("nbs_pmi_request_not_reviewed")
    label, number, source_label = CATEGORIES[index]
    if (request.get("id") != "s11-shape15::category" + str(index) or request.get("chart_id") != "s11-shape15"
            or request.get("series_name") != "snapshot" or request.get("definition") != "PMI分项指数：" + label
            or set(request.get("definition_aliases", [])) != {label, label + "指数"}):
        raise ValueError("nbs_pmi_request_not_reviewed")
    return number, source_label


def _candidate(page, request, table, replay, ri, publication_quote):
    number, count, caption, parser, grid, _ = replay
    requested_number, label = _request(request)
    if number != requested_number: raise ValueError("nbs_pmi_wrong_indicator_table")
    column = TABLE_LABELS[number].index(label); header_label, header_ri, header_ci = grid[count - 1, column]
    row = table["rows"][ri]; marker = re.fullmatch(r"(20\d{2})年(\d{1,2})月", compact(row["cells"][0]))
    token = compact(row["cells"][column])
    if not re.fullmatch(r"\d+(?:\.\d+)?", token) or not 0 <= float(token) <= 100:
        raise ValueError("nbs_pmi_original_index_level_invalid")
    proof = {"orientation": ORIENTATION, "profile": PROFILES[number], "table_index": table["table_index"],
             "row_index": ri, "column_index": column, "period_column_index": 0,
             "header_row_index": header_ri, "header_column_index": header_ci, "header_row_count": count,
             "expanded_column_index": column, "source_label": header_label,
             "header_cell_quote": table["rows"][header_ri]["cells"][header_ci],
             "header_quotes": [r["quote"] for r in table["rows"][:count]],
             "header_spans": [[list(v) for v in parser.spans[ri]] for ri in range(count)],
             "caption_quote": caption, "table_html_sha256": table["html_sha256"],
             "text_sha256": page["text_sha256"], "unit_quote": table["rows"][0]["cells"][0],
             "publication_quote": publication_quote, "statistical_scope": "中国制造业", "seasonal_adjustment": "经季节调整"}
    return {"request_id": request["id"], "definition": request["definition"],
            "period": f"{int(marker[1])}-{int(marker[2]):02d}", "value": float(token), "value_text": token,
            "unit": "指数", "quote": row["quote"], "definition_quote": proof["header_cell_quote"],
            "period_quote": row["cells"][0], "table_proof": proof}


def reviewed_pmi_candidates(page, requests, cutoff_date=None, report_month=None):
    try: published, publication_quote = _receipt(page, cutoff_date)
    except (ValueError, KeyError, TypeError): return []
    result = []
    for table in page.get("tables", []):
        try: replay = _table(page, table)
        except (ValueError, KeyError, TypeError, IndexError): continue
        for request in requests:
            try:
                number, _ = _request(request)
                if replay[0] != number: continue
                bound = request.get("history_count", 3)
                if type(bound) is not int or not 1 <= bound <= 24: raise ValueError("nbs_pmi_history_window_invalid")
                rows = [(replay[1] + index, period) for index, period in enumerate(replay[5])
                        if period <= published.strftime("%Y-%m") and (not report_month or period <= str(report_month))]
                for ri, period in rows[-bound:]:
                    result.append(_candidate(page, request, table, replay, ri, publication_quote))
            except (ValueError, KeyError, TypeError, IndexError): continue
    # Identical desktop/mobile tables are one publisher fact. Contradictions
    # are preserved for the independent source conflict gate, never averaged.
    seen = set(); unique = []
    for candidate in result:
        key = (candidate["request_id"], candidate["period"], candidate["value"])
        if key not in seen: unique.append(candidate); seen.add(key)
    return unique


def verify_pmi_table_candidate(candidate, request, page, cutoff_date=None, report_month=None):
    published, publication_quote = _receipt(page, cutoff_date); _request(request)
    proof = candidate.get("table_proof", {})
    if proof.get("orientation") != ORIENTATION or proof.get("profile") not in PROFILES.values():
        raise ValueError("nbs_pmi_unknown_private_profile")
    for key in ("table_index", "row_index", "column_index", "period_column_index", "header_row_index", "header_column_index", "header_row_count", "expanded_column_index"):
        if type(proof.get(key)) is not int or proof[key] < 0: raise ValueError("nbs_pmi_physical_coordinates_invalid")
    try:
        table = page["tables"][proof["table_index"]]
        if table["table_index"] != proof["table_index"]: raise ValueError("nbs_pmi_table_index_mismatch")
        replay = _table(page, table)
        if proof["row_index"] < replay[1]: raise ValueError("nbs_pmi_header_is_not_data")
        expected = _candidate(page, request, table, replay, proof["row_index"], publication_quote)
    except (KeyError, IndexError, TypeError) as exc:
        raise ValueError("nbs_pmi_physical_coordinates_invalid") from exc
    if expected["period"] > published.strftime("%Y-%m") or (report_month and expected["period"] > str(report_month)):
        raise ValueError("nbs_pmi_month_after_publication_or_target")
    value = candidate.get("value")
    if type(value) not in {int, float} or not math.isfinite(value): raise ValueError("nbs_pmi_candidate_value_invalid")
    expected_metadata = {"series_name": request["series_name"], "receipt_id": page["receipt_id"], "source_url": page["url"],
                         "source_grade": "primary", "publisher_id": "primary:" + urlparse(page["url"]).hostname,
                         "published_at": page["published_at"], "observation_kind": "actual"}
    for key in METADATA:
        if key in candidate and candidate[key] != expected_metadata[key]: raise ValueError("nbs_pmi_output_provenance_changed")
    content = {key: value for key, value in candidate.items() if key not in METADATA}
    if json.dumps(content, ensure_ascii=False, sort_keys=True, allow_nan=False) != json.dumps(expected, ensure_ascii=False, sort_keys=True, allow_nan=False):
        raise ValueError("nbs_pmi_candidate_not_exact_original_role_cell")
    return {"table": table, "semantic_text": "\n".join([proof["caption_quote"], *proof["header_quotes"],
                                                          expected["period_quote"], expected["quote"]]),
            "reviewed_period_and_definition": True, "observation_kind": "actual"}
