"""Exact original Customs USD trade tables, replayable without a model.

The preliminary Trade Mode profile reads national monthly year-on-year cells.
The Monthly Bulletin profile reads the published monthly Balance, never the
cumulative Balance or export-minus-import. USD million -> 亿美元 is exact
unit scaling and carries an independently replayed one-cell derivation.
Original article publication dates must be established by the receipt reader.
"""
from decimal import Decimal
from datetime import date
from hashlib import sha256
from html.parser import HTMLParser
import math
import re
from urllib.parse import urlparse

ORIENTATION = "official_customs_trade_rows"
YOY_PROFILE = "customs_trade_mode_usd_yoy_v1"
BALANCE_PROFILE = "customs_monthly_usd_balance_v1"
PROFILES = {YOY_PROFILE, BALANCE_PROFILE}
MONTHS = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")
SERIES = {
    "出口金额:当月同比(%,右轴)": ("%", "export_yoy", 5),
    "进口金额:当月同比(%,右轴)": ("%", "import_yoy", 6),
    "贸易差额(亿美元)": ("亿美元", "monthly_balance", 4),
}
NUMERIC = r"[+-]?(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?"


def compact(value):
    return re.sub(r"\s+", "", str(value))


class _Rows(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.rows, self.spans = [], []
        self.row = self.cell = None
        self.table_depth = 0

    def handle_starttag(self, tag, attrs):
        if tag == "table":
            self.table_depth += 1
            if self.table_depth != 1:
                raise ValueError("customs_nested_table")
        elif tag == "tr":
            if self.row is not None:
                raise ValueError("customs_nested_row")
            self.row = []
            self.rows.append(self.row)
            self.spans.append([])
        elif tag in {"td", "th"} and self.row is not None:
            if self.cell is not None:
                raise ValueError("customs_nested_cell")
            attrs = dict(attrs)
            spans = tuple(int(attrs.get(key, "1")) for key in ("rowspan", "colspan"))
            if any(x < 1 or x > 20 for x in spans):
                raise ValueError("customs_invalid_spans")
            self.spans[-1].append(spans)
            self.cell = []

    def handle_endtag(self, tag):
        if tag in {"td", "th"} and self.cell is not None:
            self.row.append("".join(self.cell))
            self.cell = None
        elif tag == "tr":
            self.row = None
        elif tag == "table":
            self.table_depth -= 1

    def handle_data(self, data):
        if self.cell is not None:
            self.cell.append(data)


def _request(request, profile):
    name = request.get("series_name")
    role = SERIES.get(name)
    if (request.get("chart_id") != "s19-shape13" or role is None
            or request.get("id") != "s19-shape13::" + name
            or request.get("definition") != "美元计价进出口：" + name
            or request.get("unit") != role[0] or request.get("frequency") != "monthly"):
        raise ValueError("customs_request_not_reviewed")
    expected = BALANCE_PROFILE if role[1] == "monthly_balance" else YOY_PROFILE
    if profile != expected:
        raise ValueError("customs_request_profile_mismatch")
    return role


def _layout(page, table, profile):
    if profile not in PROFILES:
        raise ValueError("customs_unknown_profile")
    url = urlparse(page.get("url", ""))
    if (url.scheme not in {"http", "https"} or url.hostname != "english.customs.gov.cn"
            or url.username or url.password or url.query or url.fragment
            or url.port not in (None, 80 if url.scheme == "http" else 443)
            or not re.fullmatch(r"/Statics/[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}\.html", url.path)):
        raise ValueError("customs_original_publisher_unproven")
    text = page.get("text", "")
    if (not isinstance(text, str) or sha256(text.encode()).hexdigest() != page.get("text_sha256")
            or page.get("truncated") is not False):
        raise ValueError("customs_original_page_receipt_changed")
    original = table.get("source_html", "")
    if not original or sha256(original.encode()).hexdigest() != table.get("html_sha256"):
        raise ValueError("customs_original_html_hash_mismatch")
    parser = _Rows()
    parser.feed(original)
    rows = table["rows"]
    if len(rows) != len(parser.rows) or any(
            type(row.get("row_index")) is not int or row["row_index"] != index
            or [compact(x) for x in row["cells"]] != [compact(x) for x in parser.rows[index]]
            for index, row in enumerate(rows)):
        raise ValueError("customs_original_cells_changed")
    if any(compact(row["quote"]) != "|" + "|".join(compact(x) for x in parser.rows[index])
           or compact(row["quote"]) not in compact(text) for index, row in enumerate(rows)):
        raise ValueError("customs_original_quote_changed")
    if len(rows) < 5:
        raise ValueError("customs_table_layout_missing")
    caption = rows[0]["cells"][0]
    if len(rows[0]["cells"]) != 1 or len(rows[1]["cells"]) != 1:
        raise ValueError("customs_caption_or_unit_changed")
    # A table-specific caption followed only by the article publication header
    # must end the local preceding context; navigation cannot supply the scope.
    context = compact(table.get("context", ""))
    if not re.search(re.escape(compact(caption)) + r"20\d{2}/(?:0[1-9]|1[0-2])/(?:0[1-9]|[12]\d|3[01])$", context):
        raise ValueError("customs_article_caption_context_unproven")
    publication_quote = re.search(r"20\d{2}/\d{2}/\d{2}$", context)[0]
    publication = date.fromisoformat(publication_quote.replace("/", "-"))
    if page.get("published_at") != publication.isoformat():
        raise ValueError("customs_original_publication_date_changed")
    if compact(caption) + publication_quote not in compact(text):
        raise ValueError("customs_article_date_not_in_original_page")
    if profile == YOY_PROFILE:
        match = re.fullmatch(r"\(2\)China'sTotalExport&ImportValuesbyTradeMode,(" + "|".join(MONTHS) + r")(20\d{2})\(inUSD\)", compact(caption))
        if not match:
            raise ValueError("customs_trade_mode_caption_changed")
        month = MONTHS.index(match[1]) + 1
        if compact(rows[1]["cells"][0]) != "Unit:USD1Million":
            raise ValueError("customs_usd_unit_changed")
        expected = [["TradeMode", str(month), "Year-on-Year(±%)"],
                    ["Export&Import", "Export", "Import", "Export&Import", "Export", "Import"]]
        if ([compact(x) for x in rows[2]["cells"]] != expected[0]
                or [compact(x) for x in rows[3]["cells"]] != expected[1]
                or parser.spans[:4] != [[(1, 7)], [(1, 7)], [(2, 1), (1, 3), (1, 3)], [(1, 1)] * 6]
                or len(rows[4]["cells"]) != 7 or compact(rows[4]["cells"][0]) != "TotalValue"
                or parser.spans[4] != [(1, 1)] * 7):
            raise ValueError("customs_monthly_yoy_headers_changed")
        if sum(compact(row["cells"][0]) == "TotalValue" for row in rows if row["cells"]) != 1:
            raise ValueError("customs_national_total_ambiguous")
        periods = {f"{match[2]}-{month:02d}": 4}
    else:
        if compact(caption) != "1.SummaryofImportsandExports(InUSD)B：Monthly":
            raise ValueError("customs_monthly_balance_caption_changed")
        if compact(rows[1]["cells"][0]) != "Unit:US$million":
            raise ValueError("customs_usd_unit_changed")
        headers = [compact(x) for x in rows[2]["cells"]]
        if (len(headers) != 6 or headers[:5] != ["Year&Month", "Total", "Export", "Import", "Balance"]
                or not re.fullmatch(r"1to(?:[1-9]|1[0-2])", headers[5])
                or [compact(x) for x in rows[3]["cells"]] != ["Total", "Export", "Import", "Balance"]
                or parser.spans[:4] != [[(1, 9)], [(1, 9)], [(2, 1)] * 5 + [(1, 4)], [(1, 1)] * 4]):
            raise ValueError("customs_monthly_vs_cumulative_headers_changed")
        periods = {}
        for index, row in enumerate(rows[4:], 4):
            if not row["cells"] or not any(compact(x) for x in row["cells"]):
                continue
            if not compact(row["cells"][0]):
                # Official monthly summary prints unnamed YoY/MoM child rows
                # plus blank future-month placeholders. They carry NO literal
                # period, so none can become a balance observation or inherit
                # the preceding month. Only the reviewed numeric layout skips.
                if (len(row["cells"]) == 9 and parser.spans[index] == [(1, 1)] * 9
                        and all(not compact(x) or compact(x) == "-" or re.fullmatch(NUMERIC, compact(x))
                                for x in row["cells"][1:])):
                    continue
                raise ValueError("customs_unperioded_row_changed")
            match = re.fullmatch(r"(20\d{2})\.(0[1-9]|1[0-2])", compact(row["cells"][0]))
            if not match:
                # Publication footnotes are not observations.
                if index == len(rows) - 1 and len(row["cells"]) == 1:
                    continue
                raise ValueError("customs_month_row_changed")
            if len(row["cells"]) != 9 or parser.spans[index] != [(1, 1)] * 9:
                raise ValueError("customs_month_row_changed")
            period = match[1] + "-" + match[2]
            if period in periods:
                raise ValueError("customs_month_row_ambiguous")
            periods[period] = index
        if not periods:
            raise ValueError("customs_month_rows_missing")
    return {"caption": caption, "periods": periods, "parser": parser,
            "publication_date_quote": publication_quote}


def _scaled_balance(table, index, period):
    raw_text = compact(table["rows"][index]["cells"][4])
    if not re.fullmatch(NUMERIC, raw_text):
        raise ValueError("customs_missing_balance_not_zero")
    number = Decimal(raw_text.replace(",", ""))
    value_text = format(number / Decimal(100), "f")
    unit_quote = table["rows"][1]["cells"][0]
    proof = {"formula_version": 1, "kind": "exact_unit_scale", "formula": "published_monthly_balance_usd_million / 100",
             "source_unit": "US$ million", "target_unit": "亿美元", "divisor": 100,
             "input_unit": "US$ million", "output_unit": "亿美元", "scale": 0.01,
             "source_unit_quote": unit_quote, "unit_row_index": 1, "unit_column_index": 0,
             "table_html_sha256": table["html_sha256"], "period": period,
             "inputs": [{"row_index": index, "column_index": 4, "header_row_index": 2, "header_column_index": 4,
                         "header_quote": "Balance", "input_unit": "US$ million", "value_text": raw_text, "value": float(number)}],
             "value_text": value_text, "value": float(value_text)}
    return value_text, proof


def _candidate(request, table, layout, profile, period, index):
    unit, metric, column = _request(request, profile)
    row = table["rows"][index]
    if profile == BALANCE_PROFILE:
        value_text, derivation = _scaled_balance(table, index, period)
        definition_quote, period_quote = "Balance", row["cells"][0]
    else:
        value_text = compact(row["cells"][column])
        if not re.fullmatch(NUMERIC, value_text):
            raise ValueError("customs_missing_yoy_not_zero")
        definition_quote = "Export" if metric == "export_yoy" else "Import"
        period_quote = layout["caption"]
        derivation = None
    proof = {"orientation": ORIENTATION, "profile": profile, "table_index": table["table_index"],
             "row_index": index, "column_index": column, "header_row_index": 2 if derivation else 3,
             "header_column_index": 4 if derivation else column - 1,
             "period_column_index": 0, "caption_row_index": 0, "unit_row_index": 1,
             "table_html_sha256": table["html_sha256"], "metric_role": metric,
             "publication_date_quote": layout["publication_date_quote"]}
    result = {"request_id": request["id"], "period": period, "value": float(value_text.replace(",", "")),
              "value_text": value_text, "unit": unit, "definition": request["definition"],
              "quote": row["quote"], "definition_quote": definition_quote, "period_quote": period_quote,
              "table_proof": proof}
    if derivation:
        result.update({"derivation_proof": derivation, "observation_kind": "derived"})
    return result


def reviewed_public_candidates(page, requests):
    result = []
    for table in page.get("tables", []):
        for profile in sorted(PROFILES):
            try:
                layout = _layout(page, table, profile)
            except (KeyError, ValueError, TypeError, IndexError):
                continue
            for request in requests:
                for period, index in layout["periods"].items():
                    try:
                        result.append(_candidate(request, table, layout, profile, period, index))
                    except (KeyError, ValueError, TypeError, IndexError):
                        continue
    return result


def verify_public_table_candidate(candidate, request, page):
    proof = candidate.get("table_proof", {})
    profile = proof.get("profile")
    if proof.get("orientation") != ORIENTATION or profile not in PROFILES:
        raise ValueError("customs_unknown_profile")
    coordinates = ("table_index", "row_index", "column_index", "header_row_index", "header_column_index",
                   "period_column_index", "caption_row_index", "unit_row_index")
    if any(type(proof.get(key)) is not int or proof[key] < 0 for key in coordinates):
        raise ValueError("customs_coordinates_invalid")
    try:
        table = page["tables"][proof["table_index"]]
        if table["table_index"] != proof["table_index"]:
            raise ValueError("customs_table_index_changed")
        # Reparse and authenticate raw HTML and roles a second time. No cached
        # model-provided cell, column, unit or derivation is trusted here.
        layout = _layout(page, table, profile)
        period = candidate.get("period")
        if layout["periods"].get(period) != proof["row_index"]:
            raise ValueError("customs_period_row_mismatch")
        expected = _candidate(request, table, layout, profile, period, proof["row_index"])
        if proof != expected["table_proof"]:
            raise ValueError("customs_metric_coordinates_mismatch")
        number = candidate.get("value")
        if type(number) not in {int, float} or not math.isfinite(number) or number != expected["value"]:
            raise ValueError("customs_original_value_changed")
        keys = ("request_id", "period", "value_text", "unit", "definition", "quote", "definition_quote", "period_quote")
        if any(compact(candidate.get(key, "")) != compact(expected[key]) for key in keys):
            raise ValueError("customs_candidate_not_original_cell")
        derivation = expected.get("derivation_proof")
        if derivation:
            supplied = candidate.get("derivation_proof")
            if not isinstance(supplied, dict) or type(supplied.get("formula_version")) is not int or type(supplied.get("divisor")) is not int:
                raise ValueError("customs_derived_proof_changed")
            if type(supplied.get("scale")) is not float or type(supplied.get("value")) not in {int, float} or not math.isfinite(supplied["value"]):
                raise ValueError("customs_derived_proof_changed")
            for item in supplied.get("inputs", []):
                if any(type(item.get(key)) is not int for key in ("row_index", "column_index", "header_row_index", "header_column_index")):
                    raise ValueError("customs_derived_proof_changed")
                if type(item.get("value")) not in {int, float} or not math.isfinite(item["value"]):
                    raise ValueError("customs_derived_proof_changed")
            if supplied != derivation or candidate.get("observation_kind") != "derived":
                raise ValueError("customs_derived_proof_changed")
        elif candidate.get("derivation_proof") is not None or candidate.get("observation_kind") == "derived":
            raise ValueError("customs_direct_cannot_claim_derivation")
    except (KeyError, IndexError, TypeError) as error:
        raise ValueError("customs_coordinates_invalid") from error
    result = {"semantic_text": " ".join(row["quote"] for row in table["rows"][:4]) + " " + candidate["quote"],
              "table": table, "reviewed_period_and_definition": True}
    if derivation:
        result.update({"derived_value_verified": True, "derivation_proof": derivation,
                       "source_unit_quote": derivation["source_unit_quote"],
                       "exact_unit_scale_verified": True, "unit_conversion_verified": True,
                       "observation_kind": "derived"})
    return result
