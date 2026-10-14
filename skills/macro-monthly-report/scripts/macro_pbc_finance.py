"""Replay four explicitly reported PBC financial growth-rate series.

Report prose only: no balance-to-flow difference, stock table interpretation,
unit conversion, model flags, or forecast. The exact request and original
sentence are independently reconstructed during every acceptance/replay.
"""
import calendar
from datetime import date
from decimal import Decimal
from hashlib import sha256
import math
import re
from urllib.parse import urlparse

PROFILE = "pbc_finance_report_yoy_v1"
PROFILES = {
    "s26-shape11::M1:同比": ("money-m1", "货币供应量同比：M1:同比"),
    "s26-shape11::M2:同比": ("money-m2", "货币供应量同比：M2:同比"),
    "s26-shape12::M2:同比": ("money-m2", "货币与社融存量同比：M2:同比"),
    "s26-shape12::社会融资规模存量:同比": ("afre-stock", "货币与社融存量同比：社会融资规模存量:同比"),
}
NUMBER = r"[+-]?\d+(?:\.\d+)?"
M1_NOTE = "中国人民银行自统计2025年1月份数据起，启用新修订的狭义货币（M1）统计口径。修订后的M1包括：流通中货币（M0）、单位活期存款、个人活期存款、非银行支付机构客户备付金。"
OUTPUT_METADATA = {"series_name", "receipt_id", "published_at", "source_url", "source_grade", "publisher_id"}


def compact(value):
    return re.sub(r"\s+", "", str(value)).replace("−", "-")


def _request(request):
    declared = PROFILES.get(request.get("id"))
    if (not declared or request.get("definition") != declared[1]
            or request.get("unit") != "%" or request.get("frequency") != "monthly"
            or request.get("chart_id") != request["id"].split("::")[0]
            or request.get("series_name") != request["id"].split("::", 1)[1]
            or "pbc.gov.cn" not in request.get("original_publisher_domains", request.get("source_domains", []))):
        raise ValueError("pbc_finance_request_not_reviewed")
    return declared[0]


def _receipt(page):
    parsed = urlparse(page["url"])
    if parsed.scheme != "https" or (parsed.hostname or "").lower() not in {"pbc.gov.cn", "www.pbc.gov.cn"}:
        raise ValueError("pbc_finance_original_publisher_unproven")
    if not page.get("receipt_id") or not re.fullmatch(r"20\d{2}-\d{2}-\d{2}", page.get("published_at", "")):
        raise ValueError("pbc_finance_receipt_publication_required")
    published = date.fromisoformat(page["published_at"])
    digest = sha256(page["text"].encode()).hexdigest()
    if page.get("text_sha256") != digest or page.get("truncated"):
        raise ValueError("pbc_finance_receipt_text_changed")
    return published


def _report_candidates(page, requests):
    text = page["text"]
    title = text.splitlines()[0].strip()
    match = re.fullmatch(r"(20\d{2})年(上半年|\d{1,2}月)金融统计数据报告", compact(title))
    if not match:
        return []
    year = int(match[1])
    month = 6 if match[2] == "上半年" else int(match[2][:-1])
    if not 1 <= month <= 12:
        return []
    period = f"{year}-{month:02d}"
    money_sections = list(re.finditer(r"三、广义货币[^\n]*\n(?P<body>.*?)\n四、", text, re.S))
    stock_sections = list(re.finditer(r"一、社会融资规模存量[^\n]*\n(?P<body>.*?)\n二、", text, re.S))
    money = money_sections[0] if len(money_sections) == 1 else None
    stock = stock_sections[0] if len(stock_sections) == 1 else None
    note_pattern = "".join(re.escape(char) + r"\s*" for char in M1_NOTE)
    notes = list(re.finditer(note_pattern, text))
    result = []
    for request in requests:
        try:
            profile = _request(request)
        except (KeyError, ValueError, AttributeError, TypeError):
            continue
        if profile == "afre-stock":
            if not stock or re.search(r"预计|预测|估算|将为", stock["body"]):
                continue
            pattern = rf"初步统计[，,]({year}年{month}月末)社会融资规模存量为({NUMBER})万亿元[，,]同比(增长|下降)({NUMBER})%"
            matches = list(re.finditer(pattern, stock["body"]))
            if len(matches) != 1:
                continue
            located = matches[0]
            label = "社会融资规模存量"
            marker = located[1]
        else:
            if (not money or not re.match(rf"\s*{month}月末[，,]广义货币[（(]M2[）)]余额", money["body"])
                    or re.search(r"预计|预测|估算|将为", money["body"])):
                continue
            index = "M1" if profile == "money-m1" else "M2"
            label = "狭义货币" if index == "M1" else "广义货币"
            pattern = rf"({label}[（(]{index}[）)])余额({NUMBER})万亿元[，,]同比(增长|下降)({NUMBER})%"
            matches = list(re.finditer(pattern, money["body"]))
            if len(matches) != 1:
                continue
            located = matches[0]
            if index == "M1" and (period < "2025-01" or len(notes) != 1):
                continue
            label = located[1]
            marker = f"{month}月末"
        token = located[4] + "%"
        number = Decimal(located[4])
        if located[3] == "下降":
            if number < 0:
                continue  # Refuse an ambiguous double negative.
            number = -number
        proof = {"profile": PROFILE, "request_profile": profile,
                 "receipt_text_sha256": page["text_sha256"], "title_quote": title,
                 "month_marker_quote": marker, "direction": located[3],
                 "statistical_kind": "month_end_balance_yoy",
                 "m1_definition_quote": notes[0].group().strip() if profile == "money-m1" else ""}
        result.append({"request_id": request["id"], "period": period,
                       "definition": request["definition"], "unit": "%", "value": float(number),
                       "value_text": token, "quote": located.group(), "definition_quote": label,
                       "period_quote": title, "observation_kind": "actual", "pbc_finance_proof": proof})
    return result


def reviewed_finance_candidates(page, requests):
    """Unsupported/invalid public page is not a locator error: return no match."""
    try:
        _receipt(page)
        return _report_candidates(page, requests)
    except (KeyError, ValueError, TypeError, AttributeError, IndexError):
        return []


def verify_finance_candidate(candidate, request, page, cutoff, report_month):
    """Reconstruct facts; strip only independently verified core provenance."""
    _request(request)
    published = _receipt(page)
    if not isinstance(cutoff, date):
        cutoff = date.fromisoformat(str(cutoff))
    if published > cutoff:
        raise ValueError("pbc_finance_publication_after_cutoff")
    period = candidate.get("period", "")
    if not re.fullmatch(r"20\d{2}-(?:0[1-9]|1[0-2])", period):
        raise ValueError("pbc_finance_period_invalid")
    year, month = map(int, period.split("-"))
    observed_end = date(year, month, calendar.monthrange(year, month)[1])
    if period > report_month or observed_end > published:
        raise ValueError("pbc_finance_period_after_publication_or_target")
    value = candidate.get("value")
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError("pbc_finance_value_invalid")
    expected_metadata = {"series_name": request["series_name"], "receipt_id": page["receipt_id"],
                         "published_at": page["published_at"], "source_url": page["url"],
                         "source_grade": "primary", "publisher_id": "primary:" + urlparse(page["url"]).hostname.lower()}
    for key in OUTPUT_METADATA:
        if key in candidate and candidate[key] != expected_metadata[key]:
            raise ValueError("pbc_finance_output_provenance_changed")
    clean = {key: value for key, value in candidate.items() if key not in OUTPUT_METADATA}
    proof = clean.get("pbc_finance_proof")
    if not isinstance(proof, dict) or proof.get("profile") != PROFILE:
        raise ValueError("pbc_finance_proof_invalid")
    originals = [item for item in reviewed_finance_candidates(page, [request]) if item["period"] == period]
    if len(originals) != 1 or originals[0] != clean:
        raise ValueError("pbc_finance_candidate_not_original")
    # Only literal pieces used by the deterministically reviewed profile.
    semantic = [clean["quote"], clean["definition_quote"], proof["title_quote"],
                proof["month_marker_quote"], proof["m1_definition_quote"]]
    if any(piece and compact(piece) not in compact(page["text"]) for piece in semantic):
        raise ValueError("pbc_finance_semantics_not_in_page")
    return {"semantic_text": "\n".join(piece for piece in semantic if piece),
            "reviewed_period_and_definition": True, "observation_kind": "actual",
            "pbc_finance_proof": proof}
