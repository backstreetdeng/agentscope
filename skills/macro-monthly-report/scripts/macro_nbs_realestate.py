"""Strict, package-local NBS real-estate table reader.

Only national cumulative investment / new-property sales area / sales amount
yoy are reviewed. Month-end unsold stock remains explicitly unsupported.
"""
from datetime import date
from hashlib import sha256
from html.parser import HTMLParser
import math
import re
from urllib.parse import urlparse

PROFILE = "nbs_realestate_main_v1"
ORIENTATION = "official_nbs_realestate_indicator_rows"
CAPTION = r"表1\s*(20\d{2})年1[—-](\d{1,2})月份全国房地产开发和销售情况"
ROLE = {
    ("s14-shape11", "房地产"): ({"房地产开发投资"}, {"房地产开发投资（亿元）"}),
    ("s17-shape15", "商品房销售面积:累计同比"): (
        {"新建商品房销售面积", "商品房销售面积"}, {"新建商品房销售面积（万平方米）", "商品房销售面积（万平方米）"}),
    ("s17-shape15", "商品房销售额:累计同比"): (
        {"新建商品房销售额", "商品房销售额"}, {"新建商品房销售额（亿元）", "商品房销售额（亿元）"}),
}


def compact(value):
    return re.sub(r"\s+", "", str(value)).replace("−", "-").replace("％", "%")


class Rows(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.rows = []; self.spans = []; self.row = None; self.cell = None; self.depth = 0

    def handle_starttag(self, tag, attrs):
        if tag == "table":
            self.depth += 1
            if self.depth != 1: raise ValueError("realestate_nested_table_unreviewed")
        if tag in {"script", "style", "noscript"}: raise ValueError("realestate_executable_table_unreviewed")
        if tag == "tr":
            if self.row is not None: raise ValueError("realestate_nested_row")
            self.row = []; self.rows.append(self.row); self.spans.append([])
        elif tag in {"td", "th"} and self.row is not None:
            if self.cell is not None: raise ValueError("realestate_nested_cell")
            attrs = dict(attrs); spans = []
            for name in ("rowspan", "colspan"):
                value = attrs.get(name, "1")
                if not re.fullmatch(r"\d+", value) or not 1 <= int(value) <= 32:
                    raise ValueError("realestate_cell_span_invalid")
                spans.append(int(value))
            self.spans[-1].append(tuple(spans)); self.cell = []

    def handle_endtag(self, tag):
        if tag in {"td", "th"} and self.cell is not None:
            self.row.append("".join(self.cell)); self.cell = None
        elif tag == "tr":
            if self.cell is not None: raise ValueError("realestate_unclosed_cell")
            self.row = None
        elif tag == "table": self.depth -= 1

    def handle_data(self, text):
        if self.cell is not None: self.cell.append(text)


def role(request):
    key = (request.get("chart_id"), request.get("series_name"))
    if (key not in ROLE or request.get("frequency") != "monthly" or request.get("unit") != "%"
            or {compact(v) for v in request.get("definition_aliases", [])} != ROLE[key][0]
            or "累计同比" not in request.get("definition", "")):
        raise ValueError("realestate_request_not_reviewed")
    return ROLE[key][1]


def replay_table(page, table, cutoff_date=None, report_month=None):
    url = urlparse(page["url"])
    if url.scheme != "https" or (url.hostname or "").lower() not in {"stats.gov.cn", "www.stats.gov.cn"}:
        raise ValueError("realestate_original_publisher_unproven")
    original = table.get("source_html", "")
    if not original or sha256(original.encode()).hexdigest() != table.get("html_sha256"):
        raise ValueError("realestate_original_html_hash_changed")
    parser = Rows(); parser.feed(original); parser.close()
    rows = table["rows"]
    if (parser.depth or parser.row is not None or parser.cell is not None or not rows or len(rows) > 200
            or len(rows) != len(parser.rows)):
        raise ValueError("realestate_original_rows_changed")
    for i, row in enumerate(rows):
        if (row.get("row_index") != i or [compact(c) for c in row["cells"]] != [compact(c) for c in parser.rows[i]]
                or compact(row.get("quote", "")) != "|" + "|".join(compact(c) for c in parser.rows[i])):
            raise ValueError("realestate_original_cells_or_quote_changed")
        if compact(row["quote"]) not in compact(page["text"]): raise ValueError("realestate_table_not_in_page")
    match = re.search("(" + CAPTION + r")\s*$", table.get("context", ""))
    if not match or compact(match[1]) not in compact(page["text"]):
        raise ValueError("realestate_caption_locality_unproven")
    caption, year, month = match[1], int(match[2]), int(match[3])
    if not 3 <= month <= 12: raise ValueError("realestate_combined_jan_feb_unreviewed")
    period = f"{year}-{month:02d}"
    if ([compact(x) for x in rows[0]["cells"]] != ["指标", "绝对量", "同比增长（%）"]
            or parser.spans[0] != [(1, 1)] * 3
            or len(rows) < 2 or compact(rows[1]["cells"][0]) != "房地产开发投资（亿元）"):
        raise ValueError("realestate_exact_metric_headers_or_parent_changed")
    for _, labels in ROLE.values():
        if sum(bool(r["cells"] and compact(r["cells"][0]) in labels) for r in rows) != 1:
            raise ValueError("realestate_target_parent_rows_ambiguous")
    try: published = date.fromisoformat(page["published_at"])
    except (KeyError, ValueError, TypeError) as error: raise ValueError("realestate_publication_date_unverified") from error
    if period > published.isoformat()[:7]: raise ValueError("realestate_period_after_publication")
    if cutoff_date and published > date.fromisoformat(str(cutoff_date)):
        raise ValueError("realestate_publication_after_cutoff")
    if report_month and period > str(report_month): raise ValueError("realestate_period_after_target")
    return period, caption, parser


def reviewed_realestate_candidates(page, requests, cutoff_date=None, report_month=None):
    candidates = []
    for table in page.get("tables", []):
        try: period, caption, parser = replay_table(page, table, cutoff_date, report_month)
        except (ValueError, KeyError, TypeError, IndexError): continue
        for request in requests:
            try: labels = role(request)
            except ValueError: continue
            for row in table["rows"]:
                i = row["row_index"]
                if (len(row["cells"]) != 3 or compact(row["cells"][0]) not in labels
                        or parser.spans[i] != [(1, 1)] * 3): continue
                text = compact(row["cells"][2])
                if not re.fullmatch(r"[+-]?\d+(?:\.\d+)?", text): continue
                candidates.append({"request_id": request["id"], "definition": request["definition"],
                                   "period": period, "value": float(text), "value_text": text, "unit": "%",
                                   "quote": row["quote"], "definition_quote": row["cells"][0], "period_quote": caption,
                                   "table_proof": {"orientation": ORIENTATION, "profile": PROFILE,
                                       "table_index": table["table_index"], "row_index": i, "column_index": 2,
                                       "header_row_index": 0, "category_column_index": 0, "metric_role": "累计同比",
                                       "caption_quote": caption, "table_html_sha256": table["html_sha256"]}})
    return candidates


def verify_realestate_table_candidate(candidate, request, page, cutoff_date=None, report_month=None):
    labels = role(request)
    proof = candidate.get("table_proof", {})
    if proof.get("profile") != PROFILE or proof.get("orientation") != ORIENTATION:
        raise ValueError("realestate_unknown_profile")
    coordinates = ("table_index", "row_index", "column_index", "header_row_index", "category_column_index")
    if any(type(proof.get(k)) is not int or proof[k] < 0 for k in coordinates):
        raise ValueError("realestate_coordinates_invalid")
    try:
        table = page["tables"][proof["table_index"]]
        if table["table_index"] != proof["table_index"]: raise ValueError("realestate_table_index_changed")
        period, caption, parser = replay_table(page, table, cutoff_date, report_month)
        row = table["rows"][proof["row_index"]]
        if (proof["column_index"] != 2 or proof["header_row_index"] != 0 or proof["category_column_index"] != 0
                or proof.get("metric_role") != "累计同比" or len(row["cells"]) != 3
                or parser.spans[proof["row_index"]] != [(1, 1)] * 3 or compact(row["cells"][0]) not in labels):
            raise ValueError("realestate_exact_metric_row_mismatch")
        if proof.get("table_html_sha256") != table["html_sha256"] or compact(proof.get("caption_quote")) != compact(caption):
            raise ValueError("realestate_proof_hash_or_caption_changed")
        expected = {"request_id": request["id"], "definition": request["definition"], "period": period,
                    "value_text": row["cells"][2], "unit": "%", "quote": row["quote"],
                    "definition_quote": row["cells"][0], "period_quote": caption}
        if any(compact(candidate.get(k)) != compact(v) for k, v in expected.items()):
            raise ValueError("realestate_candidate_not_original_cell")
        token, value = compact(row["cells"][2]), candidate.get("value")
        if (not re.fullmatch(r"[+-]?\d+(?:\.\d+)?", token) or type(value) not in {float, int}
                or not math.isfinite(value) or value != float(token)):
            raise ValueError("realestate_original_value_changed")
    except (KeyError, TypeError, IndexError) as error:
        raise ValueError("realestate_coordinates_invalid") from error
    return {"semantic_text": row["quote"] + " " + caption + " " + table["rows"][0]["quote"], "table": table}
