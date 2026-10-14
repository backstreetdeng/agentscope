"""Strict PBC LPR announcement proof; no SHIBOR/policy-rate substitutions.

The printed announcement day, both reviewed tenors, explicit percent units and
the same page's publication timestamp are independently replayed from original
receipt text. Directory and URL dates are never observation dates.
"""
from datetime import date
from hashlib import sha256
import math
import re
from urllib.parse import urlparse

PROFILE = "pbc_lpr_announcement_v1"
ORIENTATION = "official_pbc_lpr_announcement_text"
ROLES = {
    "贷款市场报价利率(LPR):1年": ({"1年期LPR", "1年期"}, "one", "1年期"),
    "贷款市场报价利率(LPR):5年": ({"5年期以上LPR", "5年期以上"}, "five", "5年期以上"),
}
CHINESE_DATE = r"(?P<year>20\d{2})年\s*(?P<month>\d{1,2})月\s*(?P<day>\d{1,2})日"
TITLE = re.compile(CHINESE_DATE + r"全国银行间同业拆借中心受权公布贷款市场报价利率[（(]LPR[）)]公告")
STATEMENT = re.compile(
    r"中国人民银行授权全国银行间同业拆借中心公布[，,]\s*(?P<announcement_date>"
    + CHINESE_DATE + r")贷款市场报价利率[（(]LPR[）)]为[：:]\s*"
    r"(?P<one_quote>1年期LPR为(?P<one>\d+(?:\.\d+)?)(?P<one_unit>[%％]))[，,]\s*"
    r"(?P<five_quote>5年期以上LPR为(?P<five>\d+(?:\.\d+)?)(?P<five_unit>[%％]))[。.]"
    r"以上LPR在下一次发布LPR之前有效[。.]"
)
PUBLICATION = re.compile(r"(?<!\d)(20\d{2})-(\d{2})-(\d{2})\s+(\d{2}):(\d{2}):(\d{2})(?!\d)")


def _role(request):
    name = request.get("series_name")
    if name not in ROLES:
        raise ValueError("pbc_lpr_request_unreviewed")
    aliases, group, tenor = ROLES[name]
    if (request.get("chart_id") != "s30-shape18" or request.get("frequency") != "announcement_monthly"
            or request.get("unit") != "%" or set(request.get("definition_aliases", [])) != aliases
            or "贷款市场报价利率" not in request.get("definition", "") or "LPR" not in request.get("definition", "")):
        raise ValueError("pbc_lpr_request_unreviewed")
    return group, tenor


def _day(match):
    try:
        return date(int(match["year"]), int(match["month"]), int(match["day"]))
    except ValueError as error:
        raise ValueError("pbc_lpr_announcement_day_invalid") from error


def _replay(page, cutoff_date=None, report_month=None):
    parsed = urlparse(page.get("url", ""))
    if (parsed.scheme != "https" or (parsed.hostname or "").lower() not in {"pbc.gov.cn", "www.pbc.gov.cn"}
            or parsed.username is not None or parsed.password is not None or parsed.port not in {None, 443}
            or not re.fullmatch(r"/zhengcehuobisi/125207/125213/125440/3876551/\d{10,}/index\.html", parsed.path)):
        raise ValueError("pbc_lpr_original_announcement_publisher_unproven")
    text = page.get("text", "")
    if (not isinstance(text, str) or not text or page.get("truncated")
            or sha256(text.encode()).hexdigest() != page.get("text_sha256")):
        raise ValueError("pbc_lpr_original_text_hash_changed_or_incomplete")
    statements = list(STATEMENT.finditer(text))
    if len(statements) != 1:
        raise ValueError("pbc_lpr_exact_authorized_statement_ambiguous")
    statement = statements[0]
    announcement_day = _day(statement)
    titles = list(TITLE.finditer(text))
    # The page title may repeat as a browser title and an article heading. Both
    # must refer to the same announcement, never another article's date.
    if (not titles or any(_day(title) != announcement_day for title in titles)
            or any(title.end() > statement.start() for title in titles)):
        raise ValueError("pbc_lpr_same_announcement_title_unproven")
    article_title = titles[-1]
    timestamps = [m for m in PUBLICATION.finditer(text)
                  if article_title.end() <= m.start() < m.end() <= statement.start()]
    if len(timestamps) != 1:
        raise ValueError("pbc_lpr_same_article_publication_timestamp_ambiguous")
    timestamp = timestamps[0]
    try:
        publication_day = date(*(int(v) for v in timestamp.groups()[:3]))
        if not (0 <= int(timestamp[4]) <= 23 and 0 <= int(timestamp[5]) <= 59 and 0 <= int(timestamp[6]) <= 59):
            raise ValueError("invalid timestamp")
        published_at = date.fromisoformat(page["published_at"])
    except (KeyError, TypeError, ValueError) as error:
        raise ValueError("pbc_lpr_publication_day_invalid") from error
    if publication_day != announcement_day or published_at != publication_day:
        raise ValueError("pbc_lpr_publication_and_announcement_days_disagree")
    if cutoff_date and publication_day > date.fromisoformat(str(cutoff_date)):
        raise ValueError("pbc_lpr_publication_after_cutoff")
    if report_month and announcement_day.isoformat()[:7] > str(report_month):
        raise ValueError("pbc_lpr_announcement_after_report_month")
    return text, statement, article_title, timestamp, announcement_day


def _candidate(request, page, replay):
    group, tenor = _role(request)
    text, statement, title, publication, day = replay
    token = statement[group]
    value = float(token)
    if not math.isfinite(value):
        raise ValueError("pbc_lpr_non_finite_original_value")
    proof = {"profile": PROFILE, "orientation": ORIENTATION,
             "source_text_sha256": sha256(text.encode()).hexdigest(),
             "title_start": title.start(), "title_end": title.end(),
             "title_quote": title.group(0),
             "statement_start": statement.start(), "statement_end": statement.end(),
             "announcement_date_start": statement.start("announcement_date"),
             "announcement_date_end": statement.end("announcement_date"),
             "publication_start": publication.start(), "publication_end": publication.end(),
             "publication_quote": publication.group(0),
             "tenor": tenor, "metric_start": statement.start(group + "_quote"),
             "metric_end": statement.end(group + "_quote"),
             "value_start": statement.start(group), "value_end": statement.end(group),
             "unit_start": statement.start(group + "_unit"), "unit_end": statement.end(group + "_unit"),
             "unit_quote": statement[group + "_unit"]}
    return {"request_id": request["id"], "definition": request["definition"],
            "period": day.isoformat(), "value": value, "value_text": token, "unit": "%",
            "quote": statement.group(0), "definition_quote": statement[group + "_quote"],
            "period_quote": statement["announcement_date"], "published_at": page["published_at"],
            "pbc_lpr_proof": proof}


def reviewed_lpr_candidates(page, requests, cutoff_date=None, report_month=None):
    try:
        replay = _replay(page, cutoff_date, report_month)
    except (ValueError, KeyError, TypeError, IndexError):
        return []
    candidates = []
    for request in requests:
        try:
            candidates.append(_candidate(request, page, replay))
        except (ValueError, KeyError, TypeError, IndexError):
            continue
    return candidates


def verify_lpr_candidate(candidate, request, page, cutoff_date=None, report_month=None):
    proof = candidate.get("pbc_lpr_proof", {})
    if proof.get("profile") != PROFILE or proof.get("orientation") != ORIENTATION:
        raise ValueError("pbc_lpr_unknown_private_profile")
    for key in ("title_start", "title_end", "statement_start", "statement_end", "announcement_date_start",
                "announcement_date_end", "publication_start", "publication_end", "metric_start", "metric_end",
                "value_start", "value_end", "unit_start", "unit_end"):
        if type(proof.get(key)) is not int or proof[key] < 0:
            raise ValueError("pbc_lpr_original_offsets_invalid")
    replay = _replay(page, cutoff_date, report_month)
    expected = _candidate(request, page, replay)
    if proof != expected["pbc_lpr_proof"]:
        raise ValueError("pbc_lpr_original_text_binding_changed")
    for key in ("request_id", "definition", "period", "value_text", "unit", "quote",
                "definition_quote", "period_quote", "published_at"):
        if candidate.get(key) != expected[key]:
            raise ValueError("pbc_lpr_candidate_not_original_announcement")
    value = candidate.get("value")
    if type(value) not in {int, float} or not math.isfinite(value) or value != expected["value"]:
        raise ValueError("pbc_lpr_original_numeric_value_changed")
    _, statement, title, publication, _ = replay
    # Every component is an exact original substring; no synthetic semantic
    # label, invented period, rate or percent unit is added for core acceptance.
    return {"semantic_text": title.group(0) + " " + publication.group(0) + " " + statement.group(0),
            "reviewed_period_and_definition": True, "observation_kind": "actual"}
