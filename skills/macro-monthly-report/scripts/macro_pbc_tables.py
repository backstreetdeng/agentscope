"""Replay PBC AFRE flow cells and two reviewed same-row derived sums.

The official spreadsheet HTML has a month header spanning three rows. Raw
HTML cell coordinates are kept separately from expanded visual coordinates.
Total flow, RMB loans to the real economy and government bonds are direct
cells. The two explicitly versioned same-row component sums are marked as
derived and independently recomputed. Stock and cumulative tables are denied.
"""
from hashlib import sha256
from decimal import Decimal
from html.parser import HTMLParser
import math
import re
from urllib.parse import urlparse

PROFILE = "pbc_tsf_flow_v1"
ORIENTATION = "official_pbc_month_rows"
CAPTION = "社会融资规模增量统计表"
HEADERS = ("社会融资规模增量", "人民币贷款", "外币贷款（折合人民币）",
           "委托贷款", "信托贷款", "未贴现银行承兑汇票", "企业债券",
           "政府债券", "非金融企业境内股票融资", "存款类金融机构资产支持证券", "贷款核销")
NUMERIC = r"[+-]?(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?"
SUMS = {"非标融资": ("pbc_tsf_nonstandard_sum_v1", ("委托贷款", "信托贷款", "未贴现银行承兑汇票")),
        "直接融资": ("pbc_tsf_direct_sum_v1", ("企业债券", "非金融企业境内股票融资"))}


def compact(text):
    return re.sub(r"\s+", "", str(text)).replace("−", "-")


class _Rows(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.rows = []
        self.row = None
        self.cell = None
        self.depth = 0

    def handle_starttag(self, tag, attrs):
        if tag == "table":
            self.depth += 1
            if self.depth != 1:
                raise ValueError("pbc_nested_table_not_reviewed")
        if tag in {"script", "style", "noscript"}:
            raise ValueError("pbc_executable_table_not_reviewed")
        if tag == "tr":
            if self.row is not None:
                raise ValueError("pbc_invalid_row_layout")
            self.row = []
            self.rows.append(self.row)
        elif tag in {"td", "th"} and self.row is not None:
            if self.cell is not None:
                raise ValueError("pbc_invalid_cell_layout")
            attrs = dict(attrs)
            spans = {}
            for key in ("rowspan", "colspan"):
                value = attrs.get(key, "1")
                if not re.fullmatch(r"\d+", value) or not 1 <= int(value) <= 32:
                    raise ValueError("pbc_invalid_cell_span")
                spans[key] = int(value)
            self.cell = {"parts": [], **spans}

    def handle_endtag(self, tag):
        if tag in {"td", "th"} and self.cell is not None:
            self.cell["text"] = "".join(self.cell.pop("parts"))
            self.row.append(self.cell)
            self.cell = None
        elif tag == "tr":
            if self.cell is not None:
                raise ValueError("pbc_unclosed_cell")
            self.row = None
        elif tag == "table":
            self.depth -= 1

    def handle_data(self, text):
        if self.cell is not None:
            self.cell["parts"].append(text)


def _grid(rows):
    grid = {}
    for ri, row in enumerate(rows):
        column = 0
        for ci, cell in enumerate(row):
            while (ri, column) in grid:
                column += 1
            for r in range(ri, ri + cell["rowspan"]):
                for c in range(column, column + cell["colspan"]):
                    if (r, c) in grid or c >= 64:
                        raise ValueError("pbc_overlapping_cell_spans")
                    grid[r, c] = {"text": cell["text"], "row": ri, "column": ci}
            column += cell["colspan"]
    return grid


def _request_header(request):
    if request.get("frequency") != "monthly" or request.get("unit") != "亿元":
        return None
    cid, name = request.get("chart_id"), request.get("series_name")
    if cid == "s25-shape9" and name == "current":
        return HEADERS[0]
    if cid == "s25-shape10" and name in {"贷款", "政府债券"}:
        return "人民币贷款" if name == "贷款" else "政府债券"
    if cid == "s25-shape10" and name in SUMS:
        return name
    return None


def _sum_proof(request, table, layout, period, ri):
    """The two reviewed same-row sums only. No candidate-supplied formula."""
    formula_id, components = SUMS[request["series_name"]]
    row = table["rows"][ri]
    total = Decimal(0)
    inputs = []
    for component in components:
        column = HEADERS.index(component) + 1
        value_text = compact(row["cells"][column])
        if not re.fullmatch(NUMERIC, value_text):
            raise ValueError("pbc_derived_input_missing")
        number = Decimal(value_text.replace(",", ""))
        total += number
        inputs.append({"row_index": ri, "column_index": column,
                       "header_row_index": layout["header"], "header_column_index": column - 1,
                       "definition_quote": table["rows"][layout["header"]]["cells"][column - 1],
                       "value_text": value_text, "value": float(number), "period": period, "unit": "亿元"})
    return format(total, "f"), {"formula_id": formula_id, "formula_version": 1,
                               "operator": "sum", "components": list(components),
                               "table_index": table["table_index"], "table_html_sha256": table["html_sha256"],
                               "period": period, "unit": "亿元", "rounding": "none", "inputs": inputs}


def _verify_table(page, table):
    parsed = urlparse(page["url"])
    if parsed.scheme != "https" or (parsed.hostname or "").lower() not in {"pbc.gov.cn", "www.pbc.gov.cn"}:
        raise ValueError("pbc_original_publisher_unproven")
    original = table.get("source_html", "")
    if not original or sha256(original.encode()).hexdigest() != table.get("html_sha256"):
        raise ValueError("pbc_original_html_hash_mismatch")
    parser = _Rows()
    parser.feed(original)
    parser.close()
    raw = parser.rows
    rows = table["rows"]
    if (not raw or len(raw) > 500 or parser.depth != 0 or parser.cell is not None or parser.row is not None
            or [[compact(c["text"]) for c in r] for r in raw] !=
            [[compact(c) for c in r["cells"]] for r in rows]):
        raise ValueError("pbc_original_cells_changed")
    for ri, row in enumerate(rows):
        if row.get("row_index") != ri or compact(row.get("quote", "")) != "".join("|" + compact(c["text"]) for c in raw[ri]):
            raise ValueError("pbc_original_row_quote_changed")
        if compact(row["quote"]) not in compact(page["text"]):
            raise ValueError("pbc_table_not_in_page")
    grid = _grid(raw)
    caption_rows = [i for i, r in enumerate(raw) if r and compact(r[0]["text"]) == CAPTION]
    unit_rows = [i for i, r in enumerate(raw) if r and compact(r[0]["text"]) == "单位：亿元人民币"]
    header_rows = [i for i, r in enumerate(raw) if tuple(compact(c["text"]) for c in r[:11]) == HEADERS]
    if len(caption_rows) != 1 or len(unit_rows) != 1 or len(header_rows) != 1:
        raise ValueError("pbc_flow_caption_unit_headers_unproven")
    header = header_rows[0]
    if not caption_rows[0] < unit_rows[0] < header or header < 1 or len(raw) <= header + 2:
        raise ValueError("pbc_flow_header_layout_changed")
    month = grid.get((header, 0), {})
    if (month.get("row") != header - 1 or month.get("column") != 0
            or raw[header - 1][0]["rowspan"] != 3
            or "月份" not in compact(month.get("text", ""))
            or "Month" not in compact(month.get("text", ""))):
        raise ValueError("pbc_month_header_span_unproven")
    if compact(grid.get((header - 1, 2), {}).get("text", "")) != "其中Ofwhich":
        raise ValueError("pbc_component_parent_header_unproven")
    for ci, expected in enumerate(HEADERS, 1):
        node = grid.get((header, ci), {})
        if compact(node.get("text", "")) != expected or node.get("row") != header or node.get("column") != ci - 1:
            raise ValueError("pbc_metric_header_grid_changed")
    for ci, expected in ((1, "AFRE(flow)"), (2, "RMBloans"), (8, "Governmentbonds")):
        if compact(grid.get((header + 1, ci), {}).get("text", "")) != expected:
            raise ValueError("pbc_bilingual_header_mismatch")
    note_rows = [i for i, r in enumerate(raw) if r and
                 "社会融资规模增量是指一定时期内实体经济从金融体系获得的资金额" in compact(r[0]["text"])]
    if len(note_rows) != 1 or note_rows[0] <= header + 1:
        raise ValueError("pbc_real_economy_scope_unproven")
    periods = {}
    for ri in range(header + 2, note_rows[0]):
        row = raw[ri]
        if not row:
            continue
        token = compact(row[0]["text"])
        if not token:
            continue
        match = re.fullmatch(r"(20\d{2})\.(0[1-9]|1[0-2])", token)
        if not match:
            raise ValueError("pbc_month_row_layout_changed")
        period = f"{match[1]}-{match[2]}"
        if period in periods or len(row) < 12 or any(c["rowspan"] != 1 or c["colspan"] != 1 for c in row[:12]):
            raise ValueError("pbc_month_row_layout_changed")
        for ci in range(12):
            if grid.get((ri, ci), {}).get("row") != ri or grid[ri, ci]["column"] != ci:
                raise ValueError("pbc_month_row_grid_changed")
        periods[period] = ri
    if not periods:
        raise ValueError("pbc_month_rows_missing")
    return {"header": header, "caption": caption_rows[0], "unit": unit_rows[0],
            "note": note_rows[0], "periods": periods, "raw": raw, "grid": grid}


def reviewed_pbc_candidates(page, requests):
    result = []
    for table in page.get("tables", []):
        try:
            layout = _verify_table(page, table)
        except (KeyError, ValueError, TypeError, IndexError):
            continue
        for request in requests:
            header = _request_header(request)
            if header is None:
                continue
            derived = header in SUMS
            column = HEADERS.index(SUMS[header][1][0] if derived else header) + 1
            for period, ri in layout["periods"].items():
                row = table["rows"][ri]
                if derived:
                    try:
                        value_text, derivation = _sum_proof(request, table, layout, period, ri)
                    except ValueError:
                        continue
                else:
                    value_text = compact(row["cells"][column])
                if not re.fullmatch(NUMERIC, value_text):
                    continue  # Blank future months and placeholders are not zero.
                proof = {"orientation": ORIENTATION, "profile": PROFILE,
                         "table_index": table["table_index"], "row_index": ri,
                         "column_index": column, "period_column_index": 0,
                         "header_row_index": layout["header"], "header_column_index": column - 1,
                         "month_header_row_index": layout["header"] - 1,
                         "unit_row_index": layout["unit"], "caption_row_index": layout["caption"],
                         "scope_row_index": layout["note"], "table_html_sha256": table["html_sha256"]}
                candidate = {"request_id": request["id"], "period": period,
                               "value": float(value_text.replace(",", "")), "value_text": value_text,
                               "unit": "亿元", "definition": request["definition"],
                               "quote": row["quote"], "period_quote": row["cells"][0],
                               "definition_quote": table["rows"][layout["header"]]["quote"] if derived else
                                   table["rows"][layout["header"]]["cells"][column - 1],
                               "table_proof": proof}
                if derived:
                    candidate.update({"observation_kind": "derived", "derivation_proof": derivation})
                result.append(candidate)
    return result


def verify_pbc_table_candidate(candidate, request, page):
    header = _request_header(request)
    if header is None:
        raise ValueError("pbc_request_not_reviewed")
    proof = candidate.get("table_proof", {})
    if proof.get("profile") != PROFILE or proof.get("orientation") != ORIENTATION:
        raise ValueError("pbc_unknown_profile")
    keys = ("table_index", "row_index", "column_index", "period_column_index", "header_row_index",
            "header_column_index", "month_header_row_index", "unit_row_index", "caption_row_index", "scope_row_index")
    if any(type(proof.get(key)) is not int or proof[key] < 0 for key in keys):
        raise ValueError("pbc_coordinates_invalid")
    try:
        table = page["tables"][proof["table_index"]]
        if table["table_index"] != proof["table_index"]:
            raise ValueError("pbc_table_index_changed")
        layout = _verify_table(page, table)
        derived = header in SUMS
        column = HEADERS.index(SUMS[header][1][0] if derived else header) + 1
        expected_coordinates = {"column_index": column, "period_column_index": 0,
                                "header_row_index": layout["header"], "header_column_index": column - 1,
                                "month_header_row_index": layout["header"] - 1,
                                "unit_row_index": layout["unit"], "caption_row_index": layout["caption"],
                                "scope_row_index": layout["note"]}
        if any(proof[key] != value for key, value in expected_coordinates.items()):
            raise ValueError("pbc_metric_coordinates_mismatch")
        if proof.get("table_html_sha256") != table["html_sha256"]:
            raise ValueError("pbc_proof_hash_mismatch")
        period = candidate.get("period")
        if layout["periods"].get(period) != proof["row_index"]:
            raise ValueError("pbc_period_row_mismatch")
        row = table["rows"][proof["row_index"]]
        if derived:
            value_text, derivation = _sum_proof(request, table, layout, period, proof["row_index"])
            supplied = candidate.get("derivation_proof")
            # Equality alone would accept bool coordinates because True == 1.
            if not isinstance(supplied, dict) or type(supplied.get("formula_version")) is not int:
                raise ValueError("pbc_derived_proof_changed")
            if not isinstance(supplied.get("inputs"), list):
                raise ValueError("pbc_derived_proof_changed")
            for item in supplied["inputs"]:
                if not isinstance(item, dict) or any(type(item.get(k)) is not int for k in
                        ("row_index", "column_index", "header_row_index", "header_column_index")):
                    raise ValueError("pbc_derived_proof_changed")
                number = item.get("value")
                if isinstance(number, bool) or not isinstance(number, (int, float)) or not math.isfinite(number):
                    raise ValueError("pbc_derived_proof_changed")
            if supplied != derivation or candidate.get("observation_kind") != "derived":
                raise ValueError("pbc_derived_proof_changed")
        else:
            if candidate.get("observation_kind") == "derived" or candidate.get("derivation_proof") is not None:
                raise ValueError("pbc_direct_cannot_claim_derivation")
            value_text = compact(row["cells"][column])
        if not re.fullmatch(NUMERIC, value_text):
            raise ValueError("pbc_missing_value_not_zero")
        expected = {"request_id": request["id"], "unit": "亿元", "definition": request["definition"],
                    "quote": row["quote"], "period_quote": row["cells"][0],
                    "definition_quote": table["rows"][layout["header"]]["quote"] if derived else
                        table["rows"][layout["header"]]["cells"][column - 1],
                    "value_text": value_text}
        if any(compact(candidate.get(key, "")) != compact(value) for key, value in expected.items()):
            raise ValueError("pbc_candidate_not_original_cell")
        value = candidate.get("value")
        if (isinstance(value, bool) or not isinstance(value, (float, int)) or not math.isfinite(value)
                or abs(value - float(value_text.replace(",", ""))) > 1e-9):
            raise ValueError("pbc_original_value_changed")
    except (KeyError, IndexError, TypeError) as error:
        raise ValueError("pbc_coordinates_invalid") from error
    # Every part is literal evidence from this exact table. The profile mapping
    # establishes RMB loans / government bonds as AFRE components, not the
    # distinct banking-system total loan statistic. No synthetic long alias.
    semantic_rows = [layout["caption"], layout["unit"], layout["header"] - 1,
                     layout["header"], layout["header"] + 1, layout["note"]]
    result = {"semantic_text": " ".join(table["rows"][i]["quote"] for i in semantic_rows) + " " + row["quote"],
              "table": table, "reviewed_period_and_definition": True}
    if derived:
        result.update({"derived_value_verified": True, "derivation_proof": derivation,
                       "observation_kind": "derived"})
    return result
