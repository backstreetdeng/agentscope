"""Reviewed Customs USD directories; locators and original receipts, not data.

The monthly Balance family selects ONE latest published Monthly Bulletin before
checking its historical rows. Earlier vintages remain audit receipts only.
HTTP is permitted solely for two reviewed English Customs directories and their
literal /Statics/UUID.html articles; HTTPS retains normal certificate validation.
"""
from __future__ import annotations

import asyncio
from datetime import date, datetime, timezone
import hashlib
from html.parser import HTMLParser
import ipaddress
import json
from pathlib import Path
import re
import socket
from urllib.parse import urljoin, urlparse
from urllib.request import HTTPRedirectHandler, Request, build_opener

SCHEMA_VERSION = 1
SOURCE_QUERY_ID = "customs_trade"
HOST = "english.customs.gov.cn"
DIRECTORIES = {
    "customs_trade_yoy": "http://english.customs.gov.cn/statics/report/preliminary.html",
    "customs_monthly_balance": "http://english.customs.gov.cn/statics/report/monthly.html",
}
SELECTORS = {"customs_trade_yoy": "preliminarysel", "customs_monthly_balance": "monthlysel"}
DIRECTORY_TITLES = {
    "customs_trade_yoy": "(2)China'sTotalExport&ImportValuesbyTradeMode(inUSD)",
    "customs_monthly_balance": "（1）SummaryofImportsandExports(InUSD)B：Monthly",
}
MONTHS = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")
ARTICLE_PATH = re.compile(r"/Statics/[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}\.html")
FETCH_TIMEOUT = 20
MAX_BYTES = 2_000_000
VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "param", "source", "track", "wbr"}
SKIP = {"script", "style", "noscript", "template"}
SERIES = {
    "出口金额:当月同比(%,右轴)": ("%", "customs_trade_yoy"),
    "进口金额:当月同比(%,右轴)": ("%", "customs_trade_yoy"),
    "贸易差额(亿美元)": ("亿美元", "customs_monthly_balance"),
}


def _compact(text):
    return re.sub(r"\s+", "", str(text))


def _allowed(url, kind=None):
    if not isinstance(url, str) or re.search(r"[\x00-\x20\x7f\\]", url):
        return False
    try:
        parsed = urlparse(url)
        if (parsed.scheme not in {"http", "https"} or parsed.hostname != HOST
                or parsed.username is not None or parsed.password is not None
                or parsed.query or parsed.fragment
                or parsed.port not in (None, 80 if parsed.scheme == "http" else 443)):
            return False
        # Reject even empty ?/#, noncanonical host/port spelling, and escaped
        # path segments. Nothing is normalized into a more permissive URL.
        if "?" in url or "#" in url or "%" in parsed.path:
            return False
        if parsed.netloc not in {HOST, HOST + (":80" if parsed.scheme == "http" else ":443")}:
            return False
        directory = parsed.path in {urlparse(item).path for item in DIRECTORIES.values()}
        article = ARTICLE_PATH.fullmatch(parsed.path) is not None
        return article if kind == "article" else directory if kind == "directory" else directory or article
    except ValueError:
        return False


def _public(url):
    if not _allowed(url):
        raise ValueError("customs_url_not_allowed")
    addresses = socket.getaddrinfo(HOST, None, type=socket.SOCK_STREAM)
    if not addresses or any(not ipaddress.ip_address(item[4][0]).is_global for item in addresses):
        raise ValueError("customs_address_not_public")


class _Redirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        _public(newurl)
        # Only a scheme/default-port redirect of the very same reviewed path.
        # A directory cannot silently turn into another profile or login page.
        if urlparse(req.full_url).path != urlparse(newurl).path:
            raise ValueError("customs_redirect_path_changed")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def _fetch_sync(url):
    _public(url)
    request = Request(url, headers={"User-Agent": "Mozilla/5.0 MacroPublicCustomsReadOnly/1.0"})
    # Standard urllib HTTPS handler validates TLS. There is no TLS override,
    # HTTPS->HTTP fallback, authentication, script execution or WAF workaround.
    with build_opener(_Redirect()).open(request, timeout=FETCH_TIMEOUT) as response:
        final_url = response.geturl()
        _public(final_url)
        if urlparse(final_url).path != urlparse(url).path:
            raise ValueError("customs_response_path_changed")
        content_type = response.headers.get("Content-Type", "")
        if "html" not in content_type.lower() and "text" not in content_type.lower():
            raise ValueError("customs_response_not_html")
        raw = response.read(MAX_BYTES + 1)
        if len(raw) > MAX_BYTES:
            raise ValueError("customs_response_too_large")
        charset = response.headers.get_content_charset() or "utf-8"
    html = raw.decode(charset, errors="strict")
    return {"url": final_url, "requested_url": url, "raw_html": html,
            "raw_sha256": hashlib.sha256(raw).hexdigest(),
            "html_sha256": hashlib.sha256(html.encode()).hexdigest(),
            "fetched_at": datetime.now(timezone.utc).isoformat(),
            "fetch_provider": "direct-primary-publisher", "discovery_only": True}


async def _fetch(url):
    return await asyncio.wait_for(asyncio.to_thread(_fetch_sync, url), FETCH_TIMEOUT + 3)


class _DOM(HTMLParser):
    """Small static DOM with exact raw ranges; hidden script strings ignored."""
    def __init__(self, raw):
        super().__init__(convert_charrefs=True)
        self.raw = raw
        self.offsets = [0]
        for match in re.finditer("\n", raw):
            self.offsets.append(match.end())
        self.root = {"tag": "root", "attrs": {}, "children": [], "text": [], "start": 0}
        self.stack = [self.root]
        self.skip = []
        self.feed(raw)
        self.close()

    def _source_offset(self):
        line, column = self.getpos()
        return self.offsets[line - 1] + column

    def handle_starttag(self, tag, attrs):
        if tag in SKIP or self.skip:
            if tag not in VOID:
                self.skip.append(tag)
            return
        pairs = [key for key, _ in attrs]
        if len(pairs) != len(set(pairs)):
            raise ValueError("customs_duplicate_dom_attributes")
        start = self._source_offset()
        node = {"tag": tag, "attrs": dict(attrs), "children": [], "text": [],
                "start": start, "inner_start": start + len(self.get_starttag_text())}
        self.stack[-1]["children"].append(node)
        if tag not in VOID:
            self.stack.append(node)
        else:
            node.update({"end": node["inner_start"], "inner_end": node["inner_start"]})

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        if tag not in VOID:
            self.handle_endtag(tag)

    def handle_endtag(self, tag):
        if self.skip:
            # A stray closing tag cannot make template/noscript contents
            # visible. End only a tag actually present in the hidden stack.
            if tag in self.skip:
                reverse_index = self.skip[::-1].index(tag)
                del self.skip[len(self.skip) - reverse_index - 1:]
            return
        if tag in VOID:
            return
        for index in range(len(self.stack) - 1, 0, -1):
            if self.stack[index]["tag"] == tag:
                node = self.stack[index]
                node.update({"inner_end": self._source_offset(), "end": self.raw.find(">", self._source_offset()) + 1})
                del self.stack[index:]
                return

    def handle_data(self, data):
        if not self.skip:
            # Each ancestor has its own complete visible text, in DOM order.
            for node in self.stack:
                node["text"].append(data)


def _nodes(node, tag=None, css=None):
    result = []
    for child in node["children"]:
        if ((tag is None or child["tag"] == tag)
                and (css is None or css in child["attrs"].get("class", "").split())):
            result.append(child)
        result.extend(_nodes(child, tag, css))
    return result


def _text(node):
    return "".join(node["text"]).strip()


def _family(request):
    name = request.get("series_name")
    spec = SERIES.get(name)
    if (spec is None or request.get("chart_id") != "s19-shape13"
            or request.get("id") != "s19-shape13::" + name
            or request.get("definition") != "美元计价进出口：" + name
            or request.get("unit") != spec[0] or request.get("frequency") != "monthly"
            or request.get("source_domains") != ["customs.gov.cn"]):
        return ""
    return spec[1]


def extract_customs_directory(raw_html, directory_url, family, year):
    """Parse ONE unique USD row and its literal month anchors, not values."""
    if family not in DIRECTORIES or not _allowed(directory_url, "directory"):
        raise ValueError("customs_directory_not_reviewed")
    if urlparse(directory_url).path != urlparse(DIRECTORIES[family]).path:
        raise ValueError("customs_directory_family_mismatch")
    tree = _DOM(raw_html)
    selectors = [node for node in _nodes(tree.root, "select") if node["attrs"].get("id") == SELECTORS[family]]
    if len(selectors) != 1:
        raise ValueError("customs_directory_year_selector_ambiguous")
    options = _nodes(selectors[0], "option")
    chosen = [node for node in options if "selected" in node["attrs"]]
    if len(chosen) > 1 or not options:
        raise ValueError("customs_directory_year_ambiguous")
    chosen = chosen[0] if chosen else options[0]
    if (chosen["attrs"].get("value") != str(year) or _text(chosen) != str(year)):
        raise ValueError("customs_directory_year_not_requested")
    title = DIRECTORY_TITLES[family]
    matching = []
    for row in _nodes(tree.root, "tr"):
        cells = [node for node in row["children"] if node["tag"] == "td"]
        if cells and _compact(_text(cells[0])) == title:
            matching.append((row, cells))
    if len(matching) != 1 or len(matching[0][1]) != 2:
        raise ValueError("customs_directory_usd_row_ambiguous")
    row, cells = matching[0]
    if _nodes(cells[0], "a") or _nodes(cells[1], "table"):
        raise ValueError("customs_directory_nested_scope")
    links, periods = [], set()
    for anchor in _nodes(cells[1], "a"):
        month_label = _text(anchor)
        if month_label not in {month + "." for month in MONTHS}:
            raise ValueError("customs_directory_month_anchor_changed")
        period = f"{year}-{MONTHS.index(month_label[:-1]) + 1:02d}"
        if period in periods:
            raise ValueError("customs_directory_month_ambiguous")
        periods.add(period)
        href = anchor["attrs"].get("href", "")
        if href.startswith("//") or re.search(r"[\x00-\x20\x7f\\]", href):
            raise ValueError("customs_directory_article_url_not_allowed")
        url = urljoin(directory_url, href)
        if not _allowed(url, "article"):
            raise ValueError("customs_directory_article_url_not_allowed")
        links.append({"url": url, "original_href": href, "title": _text(cells[0]),
                      "directory_url": directory_url, "family": family,
                      "source_query_id": SOURCE_QUERY_ID, "discovery_period_hint": period,
                      "directory_year_quote": _text(chosen), "directory_month_quote": month_label,
                      "directory_row_html_sha256": hashlib.sha256(raw_html[row["start"]:row["end"]].encode()).hexdigest(),
                      "published_at": "", "publication_date_basis": "", "discovery_only": True})
    return links


def extract_customs_article(raw_html, url, family, locator_period, header_only=False):
    """Prove the unique real DOM title/date/content scope; dates are not guessed."""
    if family not in DIRECTORIES or not _allowed(url, "article"):
        raise ValueError("customs_article_not_reviewed")
    tree = _DOM(raw_html)
    articles = _nodes(tree.root, "div", "atcl")
    if len(articles) != 1:
        raise ValueError("customs_article_scope_ambiguous")
    article = articles[0]
    parts = {name: _nodes(article, "div", "atcl-" + name) for name in ("ttl", "date", "cnt")}
    if any(len(nodes) != 1 for nodes in parts.values()):
        raise ValueError("customs_article_components_ambiguous")
    title, day, content = (parts[name][0] for name in ("ttl", "date", "cnt"))
    if (not title.get("end") or not day.get("end") or not content.get("end")
            or not title["end"] <= day["start"] < day["end"] <= content["start"]):
        raise ValueError("customs_article_component_order_changed")
    date_quote = _text(day)
    if not re.fullmatch(r"20\d{2}/\d{2}/\d{2}", date_quote):
        raise ValueError("customs_article_publication_date_missing")
    published = date.fromisoformat(date_quote.replace("/", "-"))
    title_quote = _text(title)
    if family == "customs_trade_yoy":
        match = re.fullmatch(r"\(2\)China'sTotalExport&ImportValuesbyTradeMode,(" + "|".join(MONTHS) + r")(20\d{2})\(inUSD\)", _compact(title_quote))
        if not match or f"{match[2]}-{MONTHS.index(match[1]) + 1:02d}" != locator_period:
            raise ValueError("customs_article_yoy_period_or_scope_changed")
    elif _compact(title_quote) != "1.SummaryofImportsandExports(InUSD)B：Monthly":
        raise ValueError("customs_article_balance_scope_changed")
    content_raw = raw_html[content["inner_start"]:content["inner_end"]]
    base = {"title": title_quote, "published_at": published.isoformat(),
            "publication_date_basis": "reviewed_customs_atcl_date_dom",
            "publication_date_quote": date_quote, "article_content_html_sha256": hashlib.sha256(content_raw.encode()).hexdigest(),
            "article_content_html": content_raw, "available_periods": [],
            "publication_header_proof": {"profile": "customs_unique_atcl_header_v1",
                "title_html": raw_html[title["start"]:title["end"]],
                "date_html": raw_html[day["start"]:day["end"]],
                "raw_html_sha256": hashlib.sha256(raw_html.encode()).hexdigest(),
                "component_order": ["atcl-ttl", "atcl-date", "atcl-cnt"]}}
    if header_only:
        # Version ordering needs a proven original publication header, not a
        # successful parser for an obsolete edition's different table layout.
        return base
    matching = []
    for table in _nodes(content, "table"):
        rows = _nodes(table, "tr")
        if not rows:
            continue
        cells = [node for node in rows[0]["children"] if node["tag"] in {"td", "th"}]
        if len(cells) == 1 and _compact(_text(cells[0])) == _compact(title_quote):
            matching.append((table, rows))
    if len(matching) != 1 or _nodes(matching[0][0], "table"):
        raise ValueError("customs_article_table_scope_ambiguous")
    table, rows = matching[0]
    cells = [[node for node in row["children"] if node["tag"] in {"td", "th"}] for row in rows]
    unit = "Unit:USD1Million" if family == "customs_trade_yoy" else "Unit:US$million"
    if len(cells) < 5 or len(cells[1]) != 1 or _compact(_text(cells[1][0])) != unit:
        raise ValueError("customs_article_usd_unit_changed")
    available = []
    if family == "customs_monthly_balance":
        expected = ["Year&Month", "Total", "Export", "Import", "Balance"]
        header = [_compact(_text(node)) for node in cells[2]]
        if (len(header) != 6 or header[:5] != expected or not re.fullmatch(r"1to(?:[1-9]|1[0-2])", header[5])
                or [_compact(_text(node)) for node in cells[3]] != ["Total", "Export", "Import", "Balance"]):
            raise ValueError("customs_article_monthly_header_changed")
        for row in cells[4:]:
            first = _compact(_text(row[0])) if row else ""
            if re.fullmatch(r"20\d{2}\.(?:0[1-9]|1[0-2])", first):
                period = first.replace(".", "-")
                if period in available:
                    raise ValueError("customs_article_period_ambiguous")
                if len(row) == 9 and re.fullmatch(r"[+-]?(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?", _compact(_text(row[4]))):
                    available.append(period)
    else:
        available = [locator_period]
    table_raw = raw_html[table["start"]:table["end"]]
    return dict(base, **{
            "article_table_html_sha256": hashlib.sha256(table_raw.encode()).hexdigest(),
            "available_periods": available, "table_parse_status": "reviewed"})


def _history(report_month):
    year, month = map(int, report_month.split("-"))
    index = year * 12 + month - 1
    return [f"{(index - offset) // 12}-{(index - offset) % 12 + 1:02d}" for offset in (3, 2, 1)]


async def discover_customs_sources(requests, report_month, cutoff_date, cache_dir=None):
    """Read native directories and articles; no search or stale-cache fallback.

    Returns selected items plus raw original pages. The caller must invoke the
    reviewed table reader and generic source validator before accepting values.
    ``source_restrictions`` prohibit a later generic search from mixing a
    preliminary Balance or an earlier Monthly Bulletin into these requests.
    """
    if not re.fullmatch(r"20\d{2}-(?:0[1-9]|1[0-2])", str(report_month)):
        raise ValueError("invalid_report_month")
    cutoff = cutoff_date if isinstance(cutoff_date, date) else date.fromisoformat(str(cutoff_date))
    families = {request["id"]: _family(request) for request in requests}
    wanted = set(families.values()) - {""}
    history = _history(report_month)
    year = int(report_month[:4])
    semaphore = asyncio.Semaphore(3)
    root = Path(cache_dir).resolve() if cache_dir else None
    receipts, original_pages, issues = [], [], []

    async def fetch(url, role, family):
        async with semaphore:
            try:
                page = await _fetch(url)
                if not _allowed(page.get("url", "")) or urlparse(page["url"]).path != urlparse(url).path:
                    raise ValueError("customs_response_path_changed")
                receipt = {key: page.get(key) for key in ("url", "requested_url", "raw_sha256", "html_sha256", "fetched_at", "fetch_provider")}
                receipt.update({"status": "retrieved", "role": role, "family": family, "discovery_only": True})
                if root:
                    root.mkdir(parents=True, exist_ok=True)
                    target = root / (hashlib.sha256(url.encode()).hexdigest() + ".json")
                    temporary = target.with_suffix(".json.tmp")
                    temporary.write_text(json.dumps(page, ensure_ascii=False, indent=2), encoding="utf-8")
                    temporary.replace(target)
                    receipt["evidence_path"] = str(target)
                receipts.append(receipt)
                original_pages.append(page)
                return page, receipt
            except Exception as exc:
                receipt = {"url": url, "status": "retrieval_failed", "role": role, "family": family,
                           "error_type": type(exc).__name__, "message": str(exc), "discovery_only": True}
                receipts.append(receipt)
                return None, receipt

    async def directory(family):
        url = DIRECTORIES[family]
        page, receipt = await fetch(url, "directory", family)
        if page is None:
            issues.append({"family": family, "code": "customs_directory_retrieval_failed", "url": url})
            return []
        try:
            return extract_customs_directory(page["raw_html"], page["url"], family, year)
        except Exception as exc:
            receipt["parse_status"] = "rejected"
            issues.append({"family": family, "code": str(exc), "url": url})
            return []

    links_by_family = dict(zip(sorted(wanted), await asyncio.gather(*(directory(family) for family in sorted(wanted)))))
    # Preliminary YoY uses its explicit month caption. Balance scans every
    # listed edition, including a later month whose publication is <= cutoff.
    candidates = [item for family, links in links_by_family.items() for item in links
                  if family == "customs_monthly_balance" or item["discovery_period_hint"] in history]

    async def article(item):
        page, receipt = await fetch(item["url"], "article", item["family"])
        if page is None:
            return None
        try:
            header = extract_customs_article(page["raw_html"], page["url"], item["family"], item["discovery_period_hint"], header_only=True)
            try:
                header = extract_customs_article(page["raw_html"], page["url"], item["family"], item["discovery_period_hint"])
            except ValueError as exc:
                header.update({"table_parse_status": "rejected", "table_parse_error": str(exc)})
                receipt["table_parse_status"] = "rejected"
            selected = dict(item, url=page["url"], **header)
            selected["receipt_html_sha256"] = page["html_sha256"]
            receipt.update({key: header[key] for key in ("published_at", "publication_date_quote", "publication_date_basis")})
            return selected
        except Exception as exc:
            receipt["parse_status"] = "rejected"
            issues.append({"family": item["family"], "code": str(exc), "url": item["url"]})
            return None

    articles = await asyncio.gather(*(article(item) for item in candidates))
    selected_by_family = {family: [] for family in wanted}
    revisions = []
    selection_proof = {"family": "customs_monthly_balance", "rule": "unique_max_reviewed_atcl_date_on_or_before_cutoff",
                       "cutoff_date": cutoff.isoformat(), "required_periods": history, "selected_url": "",
                       "same_receipt_all_history": True, "older_vintages_audit_only": True}
    for item in [entry for entry in articles if entry and entry["family"] == "customs_trade_yoy"]:
        if item.get("table_parse_status") != "reviewed":
            issues.append({"family": item["family"], "code": item.get("table_parse_error", "customs_article_table_unproven"), "url": item["url"]})
        elif item["published_at"] <= cutoff.isoformat():
            selected_by_family[item["family"]].append(item)
        else:
            issues.append({"family": item["family"], "code": "customs_release_after_cutoff", "url": item["url"]})
    if "customs_trade_yoy" in wanted:
        found = {item["discovery_period_hint"] for item in selected_by_family["customs_trade_yoy"]}
        for period in history:
            if period not in found:
                issues.append({"family": "customs_trade_yoy", "code": "customs_yoy_history_missing", "period": period})
    if "customs_monthly_balance" in wanted:
        balance_pairs = [(candidate, article) for candidate, article in zip(candidates, articles)
                         if candidate["family"] == "customs_monthly_balance"]
        balance = [item for _, item in balance_pairs if item and item["published_at"] <= cutoff.isoformat()]
        revisions = [{key: item.get(key) for key in ("url", "published_at", "discovery_period_hint", "receipt_html_sha256", "available_periods", "table_parse_status", "table_parse_error")}
                     for _, item in balance_pairs if item]
        # Unreadable header means its date/latest position is unknown. Never
        # hide that uncertainty with an older readable table.
        if not balance_pairs or any(item is None for _, item in balance_pairs):
            issues.append({"family": "customs_monthly_balance", "code": "customs_latest_balance_version_unproven"})
        elif not balance:
            issues.append({"family": "customs_monthly_balance", "code": "customs_balance_no_release_before_cutoff"})
        else:
            maximum = max(item["published_at"] for item in balance)
            latest = [item for item in balance if item["published_at"] == maximum]
            if len(latest) != 1:
                issues.append({"family": "customs_monthly_balance", "code": "customs_latest_balance_version_ambiguous", "published_at": maximum})
            else:
                item = latest[0]
                selection_proof.update({"selected_url": item["url"], "published_at": item["published_at"],
                                        "selected_receipt_html_sha256": item["receipt_html_sha256"]})
                if item.get("table_parse_status") != "reviewed":
                    issues.append({"family": "customs_monthly_balance", "code": "customs_latest_balance_table_unproven",
                                   "reason": item.get("table_parse_error"), "url": item["url"]})
                elif not set(history) <= set(item["available_periods"]):
                    issues.append({"family": "customs_monthly_balance", "code": "customs_latest_balance_history_incomplete",
                                   "missing_periods": sorted(set(history) - set(item["available_periods"]))})
                else:
                    selected_by_family["customs_monthly_balance"] = [item]
    by_request = {}
    for request in requests:
        rid, family = request["id"], families[request["id"]]
        items = selected_by_family.get(family, [])
        by_request[rid] = {"family": family, "source_query_id": SOURCE_QUERY_ID,
                           "items": items, "discovery_urls": [item["url"] for item in items],
                           "required_periods": history,
                           "source_restrictions": {"exclusive_reviewed_discovery": bool(family),
                               "allowed_source_urls": [item["url"] for item in items],
                               "disallow_generic_search_history_mix": bool(family),
                               "balance_same_vintage_required": family == "customs_monthly_balance"},
                           "issues": [issue for issue in issues if issue["family"] == family] if family else [{"code": "customs_request_not_reviewed"}]}
    return {"schema_version": SCHEMA_VERSION, "source_query_id": SOURCE_QUERY_ID,
            "report_month": report_month, "cutoff_date": cutoff.isoformat(), "discovery_only": True,
            "by_request": by_request, "receipts": receipts, "original_pages": original_pages,
            "balance_selection_proof": selection_proof, "balance_revision_receipts": revisions,
            "issues": issues}
