"""Reviewed NBS industrial-production tables, not generic model transposition.

Original HTML, exact caption, row, month/cumulative header and numeric column
are independently replayed. No statistical observations come from a template.
"""
from hashlib import sha256
from html.parser import HTMLParser
import re
from urllib.parse import urlparse

CHARTS = {"s13-shape10", "s13-shape17", "overview"}
CAPTION = r"20\d{2}年\s*\d{1,2}月份?\s*规模以上工业生产主要数据"


def compact(text):
    return re.sub(r"\s+", "", str(text)).replace("％", "%").replace("−", "-")


def label(text):
    value=compact(text)
    value=re.sub(r"[（(](?:万吨|亿千瓦时)[）)]$","",value)
    return re.sub(r"^(?:其中[:：]|[一二三四五六七八九十]+[、.]|\d+[、.])", "", value)


class Rows(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.rows=[];self.row=None;self.cell=None

    def handle_starttag(self,tag,attrs):
        if tag=="tr":self.row=[];self.rows.append(self.row)
        elif tag in {"td","th"} and self.row is not None:self.cell=[]

    def handle_endtag(self,tag):
        if tag in {"td","th"} and self.cell is not None:
            self.row.append("".join(self.cell));self.cell=None
        elif tag=="tr":self.row=None

    def handle_data(self,text):
        if self.cell is not None:self.cell.append(text)


def _caption(table):
    matches=list(re.finditer(CAPTION, str(table.get("context",""))))
    return matches[-1].group() if matches else ""


def _reviewed(request):
    return request.get("chart_id") in CHARTS and request.get("frequency")=="monthly" and request.get("unit")=="%"


def _verify_table(page,table):
    if (urlparse(page["url"]).hostname or "").lower() not in {"stats.gov.cn","www.stats.gov.cn"}:
        raise ValueError("nbs_industry_original_publisher_unproven")
    original=table.get("source_html","")
    if not original or sha256(original.encode()).hexdigest()!=table.get("html_sha256"):
        raise ValueError("nbs_industry_original_html_hash_mismatch")
    parser=Rows();parser.feed(original)
    if [[compact(x) for x in r] for r in parser.rows]!=[[compact(x) for x in r["cells"]] for r in table["rows"]]:
        raise ValueError("nbs_industry_original_cells_changed")
    caption=_caption(table)
    if not caption or compact(caption) not in compact(page["text"]):
        raise ValueError("nbs_industry_caption_unproven")
    match=re.search(r"(20\d{2})年\s*(\d{1,2})月",caption)
    year,month=int(match[1]),int(match[2])
    rows=table["rows"]
    # This reviewed NBS layout has a row-spanned indicator header, then the
    # monthly and YTD absolute/yoy columns. Do not guess a changed table layout.
    if len(rows)<3 or [compact(x) for x in rows[0]["cells"]]!=["指标",f"{month}月",f"1—{month}月"]:
        raise ValueError("nbs_industry_period_headers_changed")
    if [compact(x) for x in rows[1]["cells"]]!=["绝对量","同比增长（%）","绝对量","同比增长（%）"]:
        raise ValueError("nbs_industry_metric_headers_changed")
    return f"{year}-{month:02d}",caption


def reviewed_nbs_candidates(page,requests):
    result=[]
    for table in page.get("tables",[]):
        try:period,caption=_verify_table(page,table)
        except (KeyError,ValueError,TypeError,IndexError):continue
        for request in requests:
            if not _reviewed(request):continue
            aliases={label(x) for x in request.get("definition_aliases",[]) if x}
            column=4 if "累计" in request.get("definition","") else 2
            for row in table["rows"][2:]:
                if len(row["cells"])!=5 or label(row["cells"][0]) not in aliases:continue
                value_text=compact(row["cells"][column])
                if not re.fullmatch(r"[+-]?\d+(?:\.\d+)?",value_text):continue
                proof={"orientation":"official_indicator_rows","profile":"nbs_industrial_production_v1",
                       "table_index":table["table_index"],"row_index":row["row_index"],"column_index":column,
                       "category_column_index":0,"header_row_index":1,"caption_quote":caption,
                       "table_html_sha256":table["html_sha256"]}
                result.append({"request_id":request["id"],"period":period,"value":float(value_text),
                               "unit":request["unit"],"definition":request["definition"],
                               "quote":row["quote"],"definition_quote":row["cells"][0],
                               "period_quote":caption,"value_text":value_text,"table_proof":proof})
    return result


def verify_nbs_table_candidate(candidate,request,page):
    if not _reviewed(request):raise ValueError("nbs_industry_request_not_reviewed")
    proof=candidate.get("table_proof",{})
    if proof.get("profile")!="nbs_industrial_production_v1":raise ValueError("nbs_industry_unknown_profile")
    keys=("table_index","row_index","column_index","category_column_index","header_row_index")
    if any(type(proof.get(key)) is not int or proof[key]<0 for key in keys):
        raise ValueError("nbs_industry_coordinates_invalid")
    try:
        table=page["tables"][proof["table_index"]]
        period,caption=_verify_table(page,table)
        row=table["rows"][proof["row_index"]]
        column=4 if "累计" in request.get("definition","") else 2
        if (proof["column_index"]!=column or proof["category_column_index"]!=0 or proof["header_row_index"]!=1
                or proof["row_index"]<2 or len(row["cells"])!=5):
            raise ValueError("nbs_industry_metric_column_mismatch")
        if proof.get("table_html_sha256")!=table["html_sha256"] or compact(proof.get("caption_quote"))!=compact(caption):
            raise ValueError("nbs_industry_proof_hash_mismatch")
        aliases={label(x) for x in request.get("definition_aliases",[]) if x}
        if label(row["cells"][0]) not in aliases:raise ValueError("nbs_industry_exact_row_mismatch")
        expected={"period":period,"period_quote":caption,"quote":row["quote"],"definition_quote":row["cells"][0],"value_text":row["cells"][column]}
        if any(compact(candidate.get(key))!=compact(value) for key,value in expected.items()):
            raise ValueError("nbs_industry_candidate_not_original_cell")
    except (KeyError,IndexError,TypeError) as error:
        raise ValueError("nbs_industry_coordinates_invalid") from error
    # Literal headers establish scope/unit for the exact cell. Context is not
    # borrowed from an unrelated paragraph or the full page.
    # The reviewed child industries inherit the explicit parent metric in this
    # same table. Product-output rows must never inherit industrial added value.
    scope=""
    children={"采矿业","制造业","高技术制造业","电力、热力、燃气及水生产和供应业"}
    if request.get("chart_id") in {"s13-shape10","s13-shape17"} and label(row["cells"][0]) in children:
        parent=table["rows"][2]
        if label(parent["cells"][0])!="规模以上工业增加值" or len(parent["cells"])!=5:
            raise ValueError("nbs_industry_parent_metric_unproven")
        scope=parent["cells"][0]
    return {"semantic_text":row["quote"]+" "+caption+" "+scope+" "+table["rows"][1]["quote"]+
            " "+("累计" if column==4 else "当月同比")+" "+table["rows"][0]["quote"],
            "table":table}
