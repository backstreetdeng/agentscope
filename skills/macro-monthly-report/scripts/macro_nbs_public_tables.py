"""Narrow, replayable NBS retail/PPI table profiles; no model inference.

Each candidate binds an original HTML table hash, exact caption, physical
row/column, merged header roles, period, unit and reviewed statistical scope.
Publication dates remain the responsibility of the original-page receipt.
"""
from hashlib import sha256
from html.parser import HTMLParser
import math
import re
from urllib.parse import urlparse

ORIENTATION = "official_public_indicator_rows"
PROFILES = {"nbs_retail_main_v1", "nbs_macro_retail_v1", "nbs_ppi_v1"}
CAPTIONS = {
    "nbs_retail_main_v1": r"20\d{2}年\s*\d{1,2}月份?社会消费品零售总额主要数据",
    "nbs_macro_retail_v1": r"20\d{2}年\s*(?:1[—-])?\d{1,2}月份?(?:及上半年)?主要指标数据",
    "nbs_ppi_v1": r"20\d{2}年\s*\d{1,2}月份?工业生产者价格主要数据",
}
RETAIL_CATEGORIES = {
    "家具类", "家用电器和音像器材类", "建筑及装潢材料类", "粮油食品类",
    "日用品类", "通讯器材类", "金银珠宝类", "汽车类", "石油及制品类",
    # The aggregate is distinct from 服装类; no semantic widening is permitted.
    "服装鞋帽针纺织品类",
}


def compact(value):
    return re.sub(r"\s+", "", str(value)).replace("％", "%").replace("−", "-")


def label(value):
    text = compact(value)
    text = re.sub(r"^(?:其中[:：]|[一二三四五六七八九十]+[、.]|\d+[、.])", "", text)
    text = re.sub(r"[（(]亿元[）)]$", "", text)
    return text.replace("、", "").replace("，", "").replace(",", "")


class _Rows(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.rows = []
        self.spans = []
        self.row = None
        self.cell = None

    def handle_starttag(self, tag, attrs):
        if tag == "tr":
            if self.row is not None:
                raise ValueError("nbs_public_nested_rows")
            self.row = []
            self.rows.append(self.row)
            self.spans.append([])
        elif tag in {"td", "th"} and self.row is not None:
            if self.cell is not None:
                raise ValueError("nbs_public_nested_cells")
            attributes = dict(attrs)
            spans = tuple(int(attributes.get(key, "1")) for key in ("rowspan", "colspan"))
            if any(x < 1 for x in spans):
                raise ValueError("nbs_public_invalid_spans")
            self.spans[-1].append(spans)
            self.cell = []

    def handle_endtag(self, tag):
        if tag in {"td", "th"} and self.cell is not None:
            self.row.append("".join(self.cell))
            self.cell = None
        elif tag == "tr":
            self.row = None

    def handle_data(self, data):
        if self.cell is not None:
            self.cell.append(data)


def _table(page, table, profile):
    if profile not in PROFILES:
        raise ValueError("nbs_public_unknown_profile")
    if (urlparse(page.get("url", "")).hostname or "").lower() not in {"stats.gov.cn", "www.stats.gov.cn"}:
        raise ValueError("nbs_public_original_publisher_unproven")
    original = table.get("source_html", "")
    if not original or sha256(original.encode()).hexdigest() != table.get("html_sha256"):
        raise ValueError("nbs_public_original_html_hash_mismatch")
    parser = _Rows()
    parser.feed(original)
    rows = table["rows"]
    if len(rows) != len(parser.rows) or any(
        row.get("row_index") != i or [compact(x) for x in row["cells"]] != [compact(x) for x in parser.rows[i]]
        for i, row in enumerate(rows)
    ):
        raise ValueError("nbs_public_original_cells_changed")
    if any(compact(row.get("quote", "")) != "|" + "|".join(compact(x) for x in parser.rows[i])
           for i, row in enumerate(rows)):
        raise ValueError("nbs_public_original_row_quote_changed")
    # The caption must finish this table's local preceding context. A title
    # elsewhere in the full page cannot provide statistical scope or period.
    match = re.search("(" + CAPTIONS[profile] + r")\s*$", table.get("context", ""))
    if not match:
        raise ValueError("nbs_public_exact_caption_unproven")
    caption = match.group(1)
    if compact(caption) not in compact(page.get("text", "")):
        raise ValueError("nbs_public_caption_not_in_page")
    date = re.search(r"(20\d{2})年\s*(?:1[—-])?(\d{1,2})月", caption)
    year, month = int(date[1]), int(date[2])
    if not 3 <= month <= 12:
        raise ValueError("nbs_public_combined_jan_feb_not_reviewed")
    if profile == "nbs_ppi_v1":
        expected = ["", "环比涨跌幅（%）", "同比涨跌幅（%）", f"1—{month}月同比涨跌幅（%）"]
        if len(rows) < 3 or [compact(x) for x in rows[0]["cells"]] != expected or parser.spans[0] != [(1, 1)] * 4:
            raise ValueError("nbs_public_ppi_headers_changed")
        if label(rows[1]["cells"][0]) != "工业生产者出厂价格":
            raise ValueError("nbs_public_ppi_parent_unproven")
    else:
        if len(rows) < 3 or [compact(x) for x in rows[0]["cells"]] != ["指标", f"{month}月", f"1—{month}月"]:
            raise ValueError("nbs_public_retail_period_headers_changed")
        if parser.spans[0] != [(2, 1), (1, 2), (1, 2)] or parser.spans[1] != [(1, 1)] * 4:
            raise ValueError("nbs_public_retail_header_merge_changed")
        absolute = "绝对量（亿元）" if profile == "nbs_retail_main_v1" else "绝对量"
        if [compact(x) for x in rows[1]["cells"]] != [absolute, "同比增长（%）", absolute, "同比增长（%）"]:
            raise ValueError("nbs_public_retail_metric_headers_changed")
    return f"{year}-{month:02d}", caption, parser


def _role(request, profile):
    if request.get("frequency") != "monthly":
        raise ValueError("nbs_public_request_frequency_unreviewed")
    cid = request.get("chart_id")
    name = request.get("series_name", "")
    aliases = {label(x) for x in request.get("definition_aliases", []) if x}
    if profile == "nbs_ppi_v1":
        if request.get("unit") != "%":
            raise ValueError("nbs_public_request_unit_unreviewed")
        if cid == "s22-shape9" and name in {"PPI同比", "PPI环比"} and aliases == {"工业生产者出厂价格", "PPI"}:
            return {"工业生产者出厂价格"}, 1 if name == "PPI环比" else 2, "环比" if name == "PPI环比" else "同比", "ppi"
        if (cid == "s22-shape10" and name in {"全部工业品", "生产资料", "生活资料"}
                and aliases == ({"工业生产者出厂价格", "全部工业品"} if name == "全部工业品" else {name})):
            return {"工业生产者出厂价格" if name == "全部工业品" else name}, 2, "同比", "ppi"
    else:
        if cid == "s15-shape9" and aliases == {"社会消费品零售总额"}:
            roles = {
                "社会消费品零售总额:当月值": (1, "亿元", "当月值"),
                "社会消费品零售总额:当月同比(%,右轴)": (2, "%", "当月同比"),
                "社会消费品零售总额:累计同比(%,右轴)": (4, "%", "累计同比"),
            }
            if name in roles and request.get("unit") == roles[name][1]:
                column, _, metric = roles[name]
                return aliases, column, metric, "retail_total"
        if cid == "overview" and aliases == {"社会消费品零售总额"} and request.get("unit") == "%" and "当月同比" in request.get("definition", ""):
            return aliases, 2, "当月同比", "retail_total"
        if cid == "s16-shape8" and request.get("unit") == "%" and name == "snapshot":
            if aliases == {"零售总额", "社会消费品零售总额"}:
                return {"社会消费品零售总额"}, 2, "当月同比", "retail_total"
            if aliases == {"餐饮收入"}:
                return aliases, 2, "当月同比", "retail_total"
            if aliases == {"商品零售"}:
                return {"商品零售额"}, 2, "当月同比", "retail_total"
            if len(aliases) == 1 and aliases <= RETAIL_CATEGORIES and profile == "nbs_retail_main_v1":
                return aliases, 2, "当月同比", "retail_limited_category"
    raise ValueError("nbs_public_request_not_reviewed")


def _scope(table, row_index, profile, kind):
    rows = table["rows"]
    if kind == "ppi":
        # Production/living materials belong to 出厂价格, not 购进价格.
        stop = next((i for i, row in enumerate(rows[2:], 2) if label(row["cells"][0]) == "工业生产者购进价格"), len(rows))
        if not 1 <= row_index < stop:
            raise ValueError("nbs_public_ppi_wrong_section")
        return rows[1]["cells"][0]
    parents = [i for i, row in enumerate(rows[2:], 2) if row["cells"] and label(row["cells"][0]) == "社会消费品零售总额"]
    if len(parents) != 1:
        raise ValueError("nbs_public_retail_parent_ambiguous")
    parent = parents[0]
    if profile == "nbs_macro_retail_v1" and not compact(rows[parent]["cells"][0]).endswith("（亿元）"):
        raise ValueError("nbs_public_retail_unit_parent_unproven")
    stop = next((i for i in range(parent + 1, len(rows)) if re.match(r"^[一二三四五六七八九十]+、", compact(rows[i]["cells"][0]))), len(rows))
    if not parent <= row_index < stop:
        raise ValueError("nbs_public_retail_wrong_section")
    if kind == "retail_limited_category":
        limited = [i for i in range(parent, row_index) if label(rows[i]["cells"][0]) == "限额以上单位商品零售额"]
        if len(limited) != 1:
            raise ValueError("nbs_public_limited_scope_unproven")
        # Only direct category rows in this same reviewed child block inherit it.
        if any(label(rows[i]["cells"][0]).startswith("限额以上") for i in range(limited[0] + 1, row_index)):
            raise ValueError("nbs_public_limited_scope_changed")
        return rows[limited[0]]["cells"][0]
    return rows[parent]["cells"][0]


def reviewed_public_candidates(page, requests):
    result = []
    for table in page.get("tables", []):
        for profile in sorted(PROFILES):
            try:
                period, caption, parser = _table(page, table, profile)
            except (KeyError, ValueError, TypeError, IndexError):
                continue
            for request in requests:
                try:
                    aliases, column, metric, kind = _role(request, profile)
                except ValueError:
                    continue
                for index, row in enumerate(table["rows"]):
                    if len(row["cells"]) != (4 if profile == "nbs_ppi_v1" else 5) or label(row["cells"][0]) not in aliases:
                        continue
                    try:
                        _scope(table, index, profile, kind)
                    except ValueError:
                        continue
                    if parser.spans[index] != [(1, 1)] * len(row["cells"]):
                        continue
                    value_text = compact(row["cells"][column])
                    if not re.fullmatch(r"[+-]?\d+(?:\.\d+)?", value_text):
                        continue
                    proof = {"orientation": ORIENTATION, "profile": profile, "table_index": table["table_index"],
                             "row_index": index, "column_index": column, "category_column_index": 0,
                             "header_row_index": 0 if profile == "nbs_ppi_v1" else 1,
                             "caption_quote": caption, "table_html_sha256": table["html_sha256"], "metric_role": metric}
                    result.append({"request_id": request["id"], "period": period, "value": float(value_text),
                                   "unit": request["unit"], "definition": request["definition"],
                                   "quote": row["quote"], "definition_quote": row["cells"][0],
                                   "period_quote": caption, "value_text": value_text, "table_proof": proof})
    return result


def verify_public_table_candidate(candidate, request, page):
    proof = candidate.get("table_proof", {})
    profile = proof.get("profile")
    if proof.get("orientation") != ORIENTATION or profile not in PROFILES:
        raise ValueError("nbs_public_unknown_profile")
    keys = ("table_index", "row_index", "column_index", "category_column_index", "header_row_index")
    if any(type(proof.get(key)) is not int or proof[key] < 0 for key in keys):
        raise ValueError("nbs_public_coordinates_invalid")
    try:
        table = page["tables"][proof["table_index"]]
        if table["table_index"] != proof["table_index"]:
            raise ValueError("nbs_public_table_index_mismatch")
        period, caption, parser = _table(page, table, profile)
        aliases, column, metric, kind = _role(request, profile)
        index = proof["row_index"]
        row = table["rows"][index]
        if (proof["column_index"] != column or proof["category_column_index"] != 0
                or proof["header_row_index"] != (0 if profile == "nbs_ppi_v1" else 1)
                or proof.get("metric_role") != metric or len(row["cells"]) != (4 if profile == "nbs_ppi_v1" else 5)
                or parser.spans[index] != [(1, 1)] * len(row["cells"])):
            raise ValueError("nbs_public_metric_column_mismatch")
        if proof.get("table_html_sha256") != table["html_sha256"] or compact(proof.get("caption_quote")) != compact(caption):
            raise ValueError("nbs_public_proof_hash_mismatch")
        if label(row["cells"][0]) not in aliases:
            raise ValueError("nbs_public_exact_row_mismatch")
        scope = _scope(table, index, profile, kind)
        expected = {"request_id": request["id"], "period": period, "period_quote": caption, "quote": row["quote"],
                    "definition_quote": row["cells"][0], "value_text": row["cells"][column],
                    "unit": request["unit"], "definition": request["definition"]}
        if any(compact(candidate.get(key)) != compact(value) for key, value in expected.items()):
            raise ValueError("nbs_public_candidate_not_original_cell")
        value_text = compact(row["cells"][column])
        if not re.fullmatch(r"[+-]?\d+(?:\.\d+)?", value_text):
            raise ValueError("nbs_public_non_numeric_cell")
        value = candidate.get("value")
        if type(value) not in {int, float} or not math.isfinite(value) or float(value) != float(value_text):
            raise ValueError("nbs_public_numeric_value_changed")
    except (KeyError, IndexError, TypeError) as error:
        raise ValueError("nbs_public_coordinates_invalid") from error
    headers = " ".join(row["quote"] for row in table["rows"][:1 if profile == "nbs_ppi_v1" else 2])
    return {"semantic_text": row["quote"] + " " + caption + " " + scope + " " + headers + " " + metric,
            "table": table}
