"""Reviewed NBS investment / automotive-profit tables, with independent replay.

Only original, directly printed cells are supported. In particular this module
does not infer private-investment amounts or substitute infrastructure including
electricity for the template's infrastructure excluding electricity.
"""
from datetime import date
from hashlib import sha256
from html.parser import HTMLParser
import math
import re
from urllib.parse import urlparse

ORIENTATION = "official_nbs_investment_profit_rows"
PROFILES = {
    "nbs_investment_main_v1", "nbs_macro_investment_v1", "nbs_auto_profit_v1",
}
CAPTIONS = {
    "nbs_investment_main_v1":
        r"(20\d{2})年1[—-](\d{1,2})月份固定资产投资（不含农户）主要数据",
    "nbs_macro_investment_v1":
        r"(20\d{2})年(?:1[—-])?(\d{1,2})月份?(?:及上半年)?主要指标数据",
    "nbs_auto_profit_v1":
        r"表3\s*(20\d{2})年1[—-](\d{1,2})月份规模以上工业企业主要财务指标（分行业）",
}
# chart/name, exact aliases, raw unit, reviewed metric role.
ROLES = {
    ("s14-shape15", "固定资产投资累计值"):
        ({"固定资产投资"}, "亿元", "total_level"),
    ("s14-shape15", "固定资产投资累计同比(右轴)"):
        ({"固定资产投资"}, "%", "total_yoy"),
    ("s14-shape15", "民间固定资产投资累计同比(右轴)"):
        ({"民间固定资产投资", "民间投资"}, "%", "private_yoy"),
    ("s12-shape16", "民间固定资产投资:累计同比"):
        ({"民间固定资产投资", "民间投资"}, "%", "private_yoy"),
    ("s14-shape11", "制造业"):
        ({"制造业投资"}, "%", "manufacturing_yoy"),
    ("s28-shape17", "汽车制造业利润:累计同比"):
        ({"汽车制造业"}, "%", "auto_profit_yoy"),
}


def compact(value):
    return re.sub(r"\s+", "", str(value)).replace("−", "-").replace("％", "%")


def label(value):
    return re.sub(r"^(?:其中[:：]|[一二三四五六七八九十]+[、.])", "", compact(value))


class _Rows(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.rows = []
        self.spans = []
        self.row = None
        self.cell = None
        self.depth = 0

    def handle_starttag(self, tag, attrs):
        if tag == "table":
            self.depth += 1
            if self.depth != 1:
                raise ValueError("nbs_investment_profit_nested_table")
        if tag in {"script", "style", "noscript"}:
            raise ValueError("nbs_investment_profit_executable_table")
        if tag == "tr":
            if self.row is not None:
                raise ValueError("nbs_investment_profit_nested_row")
            self.row = []
            self.rows.append(self.row)
            self.spans.append([])
        elif tag in {"td", "th"} and self.row is not None:
            if self.cell is not None:
                raise ValueError("nbs_investment_profit_nested_cell")
            attrs = dict(attrs)
            spans = []
            for key in ("rowspan", "colspan"):
                raw = attrs.get(key, "1")
                if not re.fullmatch(r"\d+", raw) or not 1 <= int(raw) <= 32:
                    raise ValueError("nbs_investment_profit_invalid_span")
                spans.append(int(raw))
            self.spans[-1].append(tuple(spans))
            self.cell = []

    def handle_endtag(self, tag):
        if tag in {"td", "th"} and self.cell is not None:
            self.row.append("".join(self.cell))
            self.cell = None
        elif tag == "tr":
            if self.cell is not None:
                raise ValueError("nbs_investment_profit_unclosed_cell")
            self.row = None
        elif tag == "table":
            self.depth -= 1

    def handle_data(self, data):
        if self.cell is not None:
            self.cell.append(data)


def _request_role(request, profile):
    key = (request.get("chart_id"), request.get("series_name"))
    if key not in ROLES:
        raise ValueError("nbs_investment_profit_request_unreviewed")
    aliases, unit, kind = ROLES[key]
    if (request.get("frequency") != "monthly" or request.get("unit") != unit
            or {compact(v) for v in request.get("definition_aliases", [])} != aliases):
        raise ValueError("nbs_investment_profit_request_unreviewed")
    definition = compact(request.get("definition", ""))
    if (kind == "total_level" and "累计值" not in definition
            or kind != "total_level" and "累计同比" not in definition):
        raise ValueError("nbs_investment_profit_definition_unreviewed")
    if profile == "nbs_investment_main_v1" and kind in {
        "total_yoy", "private_yoy", "manufacturing_yoy",
    }:
        return kind
    if profile == "nbs_macro_investment_v1" and kind in {"total_level", "total_yoy"}:
        return kind
    if profile == "nbs_auto_profit_v1" and kind == "auto_profit_yoy":
        return kind
    raise ValueError("nbs_investment_profit_request_profile_unreviewed")


def _replay(page, table, profile, cutoff_date=None, report_month=None):
    if profile not in PROFILES:
        raise ValueError("nbs_investment_profit_profile_unreviewed")
    parsed_url = urlparse(page.get("url", ""))
    if parsed_url.scheme != "https" or (parsed_url.hostname or "").lower() not in {
        "stats.gov.cn", "www.stats.gov.cn",
    }:
        raise ValueError("nbs_investment_profit_original_publisher_unproven")
    original = table.get("source_html", "")
    if not original or sha256(original.encode()).hexdigest() != table.get("html_sha256"):
        raise ValueError("nbs_investment_profit_original_html_hash_changed")
    parser = _Rows()
    parser.feed(original)
    parser.close()
    rows = table["rows"]
    if (parser.depth or parser.row is not None or parser.cell is not None
            or not rows or len(rows) > 250 or len(rows) != len(parser.rows)):
        raise ValueError("nbs_investment_profit_original_rows_changed")
    for i, row in enumerate(rows):
        if (row.get("row_index") != i
                or [compact(v) for v in row["cells"]] != [compact(v) for v in parser.rows[i]]
                or compact(row.get("quote", "")) != "|" + "|".join(compact(v) for v in parser.rows[i])):
            raise ValueError("nbs_investment_profit_original_cells_or_quotes_changed")
        if compact(row["quote"]) not in compact(page.get("text", "")):
            raise ValueError("nbs_investment_profit_original_table_not_in_page")
    match = re.search("(" + CAPTIONS[profile] + r")\s*$", table.get("context", ""))
    if not match or compact(match[1]) not in compact(page.get("text", "")):
        raise ValueError("nbs_investment_profit_local_caption_unproven")
    caption, year, month = match[1], int(match[2]), int(match[3])
    if not 3 <= month <= 12:
        raise ValueError("nbs_investment_profit_combined_jan_feb_unreviewed")
    period = f"{year}-{month:02d}"
    try:
        published = date.fromisoformat(page["published_at"])
    except (KeyError, TypeError, ValueError) as error:
        raise ValueError("nbs_investment_profit_publication_date_unverified") from error
    if period > published.isoformat()[:7]:
        raise ValueError("nbs_investment_profit_period_after_publication")
    if cutoff_date and published > date.fromisoformat(str(cutoff_date)):
        raise ValueError("nbs_investment_profit_publication_after_cutoff")
    if report_month and period > str(report_month):
        raise ValueError("nbs_investment_profit_period_after_report_month")
    cells = [[compact(v) for v in r["cells"]] for r in rows]
    if profile == "nbs_investment_main_v1":
        if (len(rows) < 4 or cells[0] != ["指标", "同比增长（%）"]
                or parser.spans[0] != [(1, 1)] * 2
                or cells[1][0] != "固定资产投资（不含农户）"):
            raise ValueError("nbs_investment_profit_investment_header_or_parent_changed")
    elif profile == "nbs_macro_investment_v1":
        if (len(rows) < 3 or cells[0] != ["指标", f"{month}月", f"1—{month}月"]
                or parser.spans[0] != [(2, 1), (1, 2), (1, 2)]
                or cells[1] != ["绝对量", "同比增长（%）", "绝对量", "同比增长（%）"]
                or parser.spans[1] != [(1, 1)] * 4):
            raise ValueError("nbs_investment_profit_macro_header_period_or_merge_changed")
    else:
        if (len(rows) < 5 or cells[0] != ["行业", "营业收入", "营业成本", "利润总额"]
                or parser.spans[0] != [(3, 1), (1, 2), (1, 2), (1, 2)]
                or cells[1] != ["金额", "同比增长"] * 3
                or [v.replace("（", "(").replace("）", ")") for v in cells[2]] != ["(亿元)", "(%)"] * 3
                or parser.spans[1] != [(1, 1)] * 6 or parser.spans[2] != [(1, 1)] * 6
                or cells[3][0] != "总计"):
            raise ValueError("nbs_investment_profit_profit_hierarchical_headers_changed")
    return period, caption, parser


def _unique(rows, target):
    matches = [i for i, row in enumerate(rows) if row["cells"] and label(row["cells"][0]) == target]
    if len(matches) != 1:
        raise ValueError("nbs_investment_profit_exact_row_ambiguous")
    return matches[0]


def _binding(table, parser, profile, kind):
    rows = table["rows"]
    section = None
    if profile == "nbs_investment_main_v1":
        parent = _unique(rows, "固定资产投资（不含农户）")
        if parent != 1:
            raise ValueError("nbs_investment_profit_national_parent_changed")
        column, header_count = 1, 1
        metric, unit_quote = "累计同比", rows[0]["cells"][1]
        if kind == "total_yoy":
            index = parent
        elif kind == "private_yoy":
            index = _unique(rows, "民间投资")
            stop = _unique(rows, "按构成分")
            if not parent < index < stop or not compact(rows[index]["cells"][0]).startswith("其中："):
                raise ValueError("nbs_investment_profit_private_parent_unproven")
        else:
            index = _unique(rows, "制造业")
            section = _unique(rows, "分行业")
            stop = _unique(rows, "分登记注册统计类别")
            if (not parent < section < index < stop or len(rows[section]["cells"]) != 2
                    or compact(rows[section]["cells"][1])):
                raise ValueError("nbs_investment_profit_manufacturing_investment_scope_unproven")
        width = 2
    elif profile == "nbs_macro_investment_v1":
        index = parent = _unique(rows, "固定资产投资（不含农户）（亿元）")
        column = 3 if kind == "total_level" else 4
        metric = "累计值" if kind == "total_level" else "累计同比"
        unit_quote = rows[index]["cells"][0] if kind == "total_level" else rows[1]["cells"][3]
        header_count, width = 2, 5
        if not all(compact(c) in {"…", "...", "—", "-"} for c in rows[index]["cells"][1:3]):
            raise ValueError("nbs_investment_profit_monthly_cells_not_reviewed")
    else:
        index, parent = _unique(rows, "汽车制造业"), _unique(rows, "总计")
        column, header_count, width = 6, 3, 7
        metric, unit_quote = "累计同比", rows[2]["cells"][5]
        if parent != 3 or index <= parent:
            raise ValueError("nbs_investment_profit_industry_scope_unproven")
    row = rows[index]
    if len(row["cells"]) != width or parser.spans[index] != [(1, 1)] * width:
        raise ValueError("nbs_investment_profit_physical_metric_row_changed")
    return {"row_index": index, "column_index": column, "parent_row_index": parent,
            "section_row_index": section, "header_count": header_count,
            "metric_role": metric, "unit_quote": unit_quote}


def _numeric(raw):
    token = compact(raw)
    if not re.fullmatch(r"[+-]?\d+(?:\.\d+)?", token):
        raise ValueError("nbs_investment_profit_non_numeric_original_cell")
    value = float(token)
    if not math.isfinite(value):
        raise ValueError("nbs_investment_profit_non_finite_original_cell")
    return token, value


def _candidate(request, table, period, caption, profile, binding):
    row = table["rows"][binding["row_index"]]
    token, value = _numeric(row["cells"][binding["column_index"]])
    proof = {"orientation": ORIENTATION, "profile": profile,
             "table_index": table["table_index"], "category_column_index": 0,
             "header_row_index": 0, "caption_quote": caption,
             "table_html_sha256": table["html_sha256"], **binding}
    return {"request_id": request["id"], "definition": request["definition"],
            "period": period, "value": value, "value_text": token, "unit": request["unit"],
            "quote": row["quote"], "definition_quote": row["cells"][0],
            "period_quote": caption, "table_proof": proof}


def reviewed_investment_profit_candidates(page, requests, cutoff_date=None, report_month=None):
    result, seen = [], set()
    for table in page.get("tables", []):
        for profile in sorted(PROFILES):
            try:
                period, caption, parser = _replay(page, table, profile, cutoff_date, report_month)
            except (ValueError, KeyError, TypeError, IndexError):
                continue
            for request in requests:
                try:
                    kind = _request_role(request, profile)
                    binding = _binding(table, parser, profile, kind)
                    candidate = _candidate(request, table, period, caption, profile, binding)
                except (ValueError, KeyError, TypeError, IndexError):
                    continue
                # NBS pages can render identical desktop/mobile copies. Preserve
                # contradictory values; collapse only identical reviewed values.
                key = (request["id"], period, candidate["value_text"], profile)
                if key not in seen:
                    seen.add(key)
                    result.append(candidate)
    return result


def verify_investment_profit_table_candidate(candidate, request, page, cutoff_date=None, report_month=None):
    proof = candidate.get("table_proof", {})
    profile = proof.get("profile")
    if proof.get("orientation") != ORIENTATION or profile not in PROFILES:
        raise ValueError("nbs_investment_profit_profile_unreviewed")
    coordinates = ("table_index", "row_index", "column_index", "category_column_index",
                   "header_row_index", "parent_row_index", "header_count")
    if any(type(proof.get(k)) is not int or proof[k] < 0 for k in coordinates):
        raise ValueError("nbs_investment_profit_coordinates_invalid")
    section = proof.get("section_row_index")
    if section is not None and (type(section) is not int or section < 0):
        raise ValueError("nbs_investment_profit_coordinates_invalid")
    try:
        table = page["tables"][proof["table_index"]]
        if table["table_index"] != proof["table_index"]:
            raise ValueError("nbs_investment_profit_table_index_changed")
        period, caption, parser = _replay(page, table, profile, cutoff_date, report_month)
        kind = _request_role(request, profile)
        binding = _binding(table, parser, profile, kind)
        expected = _candidate(request, table, period, caption, profile, binding)
        if proof != expected["table_proof"]:
            raise ValueError("nbs_investment_profit_original_binding_changed")
        for key in ("request_id", "definition", "period", "value_text", "unit", "quote",
                    "definition_quote", "period_quote"):
            if compact(candidate.get(key)) != compact(expected[key]):
                raise ValueError("nbs_investment_profit_candidate_not_original_cell")
        value = candidate.get("value")
        if type(value) not in {int, float} or not math.isfinite(value) or value != expected["value"]:
            raise ValueError("nbs_investment_profit_original_numeric_value_changed")
    except (KeyError, TypeError, IndexError) as error:
        raise ValueError("nbs_investment_profit_coordinates_invalid") from error
    row = table["rows"][binding["row_index"]]
    semantic_parts = [caption, row["quote"], table["rows"][binding["parent_row_index"]]["quote"]]
    semantic_parts += [r["quote"] for r in table["rows"][:binding["header_count"]]]
    if binding["section_row_index"] is not None:
        semantic_parts.append(table["rows"][binding["section_row_index"]]["quote"])
    return {"semantic_text": " ".join(semantic_parts), "table": table,
            "reviewed_period_and_definition": True}
