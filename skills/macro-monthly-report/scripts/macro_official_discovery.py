"""Public-publisher directory discovery for the macro monthly Skill.

Directory links are locators, NEVER observations. The caller must fetch each
release and prove values, periods, definitions and publication dates separately.
This avoids stale search-engine ordering without bypassing TLS or authentication.
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
from urllib.parse import urljoin, urlparse, urlunparse
from urllib.request import HTTPRedirectHandler, Request, build_opener

SCHEMA_VERSION = 1
DIRECTORY_TIMEOUT = 20
MAX_DIRECTORY_BYTES = 2_000_000
MAX_ITEMS_PER_FAMILY = 4
ALLOWED_DOMAINS = ("stats.gov.cn", "pbc.gov.cn", "mof.gov.cn")

FAMILIES = {
    "nbs_pmi": {"charts": ("s4-shape10", "s11-shape12", "s11-shape15"), "keywords": ("采购经理指数",)},
    "nbs_gdp": {"charts": ("s10-shape7",), "keywords": ("国内生产总值", "GDP初步核算"), "required_keywords": ("初步核算",)},
    "nbs_gdp_demand": {"charts": ("s10-shape28",), "keywords": ("国民经济运行", "经济运行"), "quarterly_only": True},
    "nbs_industry": {"charts": ("s13-shape10", "s13-shape17", "overview"), "keywords": ("工业增加值", "工业生产数据")},
    # Investment-topic releases print growth rates but not the total amount.
    # The national-economy release's main-indicators appendix prints the YTD
    # amount; discover its literal directory anchor, never synthesize a URL.
    "nbs_macro_investment": {"charts": ("s14-shape15",),
                             "keywords": ("国民经济", "经济运行")},
    "nbs_investment": {"charts": ("s14-shape15", "s14-shape11"), "keywords": ("固定资产投资",)},
    "nbs_private_investment": {"charts": ("s12-shape16",), "keywords": ("固定资产投资", "企业景气")},
    "nbs_consumers": {"charts": ("s12-shape13",), "keywords": ("消费者信心", "消费者预期", "消费意愿")},
    "nbs_retail": {"charts": ("s15-shape9", "s16-shape8"), "keywords": ("社会消费品零售总额",)},
    "nbs_realestate": {"charts": ("s17-shape15",), "keywords": ("房地产市场", "房地产开发投资")},
    "nbs_housing": {"charts": ("s18-shape17", "s18-shape21"), "keywords": ("商品住宅销售价格",)},
    "nbs_cpi": {"charts": ("s21-shape11", "s21-shape12"), "keywords": ("居民消费价格",)},
    "nbs_ppi": {"charts": ("s22-shape9", "s22-shape10"), "keywords": ("工业生产者",)},
    "nbs_auto_profit": {"charts": ("s28-shape17",), "keywords": ("工业企业利润",)},
    "pbc_finance": {"charts": ("s24-shape9", "s24-shape17", "s25-shape9", "s25-shape10", "s26-shape11", "s26-shape12"),
                    "keywords": ("金融统计数据报告", "社会融资规模")},
    "pbc_lpr": {"charts": ("s30-shape18",), "keywords": ("贷款市场报价利率", "LPR")},
    "mof_fiscal": {"charts": ("s30-shape13",), "keywords": ("财政收支情况",)},
}


def _date(text):
    match = re.search(r"(?<!\d)(20\d{2})[-/.年](\d{1,2})[-/.月](\d{1,2})日?", str(text or ""))
    if match:
        try:
            return date(*(int(item) for item in match.groups()))
        except ValueError:
            pass
    return None


def _allowed(url, domains=ALLOWED_DOMAINS):
    try:
        parsed = urlparse(url)
        host = (parsed.hostname or "").lower().rstrip(".")
        return (parsed.scheme == "https" and parsed.username is None and parsed.password is None
                and parsed.port in (None, 443)
                and any(host == domain or host.endswith("." + domain) for domain in domains))
    except ValueError:
        return False


def _secure_locator(url):
    """Upgrade reviewed publishers' old HTTP hrefs, never fetch insecurely."""
    parsed = urlparse(url)
    if parsed.scheme == "http" and parsed.port in (None, 80):
        host = (parsed.hostname or "").lower()
        if (parsed.username is None and parsed.password is None
                and any(host == d or host.endswith("." + d) for d in ALLOWED_DOMAINS)):
            return urlunparse(parsed._replace(scheme="https", netloc=host))
    return url


def _public(url):
    if not _allowed(url):
        raise ValueError("directory_url_not_allowed")
    addresses = socket.getaddrinfo(urlparse(url).hostname, None, type=socket.SOCK_STREAM)
    if not addresses or any(not ipaddress.ip_address(item[4][0]).is_global for item in addresses):
        raise ValueError("directory_address_not_public")


class _Redirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        _public(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def _fetch_directory_sync(url):
    _public(url)
    request = Request(url, headers={"User-Agent": "Mozilla/5.0 MacroPublicDirectoryReadOnly/1.0"})
    with build_opener(_Redirect()).open(request, timeout=DIRECTORY_TIMEOUT) as response:
        final_url = response.geturl()
        _public(final_url)
        kind = response.headers.get("Content-Type", "")
        if "html" not in kind.lower() and "text" not in kind.lower():
            raise ValueError("directory_not_html")
        raw = response.read(MAX_DIRECTORY_BYTES + 1)
        if len(raw) > MAX_DIRECTORY_BYTES:
            raise ValueError("directory_too_large")
        charset = response.headers.get_content_charset() or "utf-8"
        if charset == "utf-8" and b"charset=gb" in raw[:4000].lower():
            charset = "gb18030"
    return {"url": final_url, "requested_url": url, "raw_html": raw.decode(charset, errors="replace"),
            "raw_sha256": hashlib.sha256(raw).hexdigest(),
            "fetched_at": datetime.now(timezone.utc).isoformat(), "fetch_provider": "direct-primary-publisher"}


async def _fetch_directory(url):
    return await asyncio.wait_for(asyncio.to_thread(_fetch_directory_sync, url), DIRECTORY_TIMEOUT + 3)


class _Links(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.links = []
        self.chunks = []
        self.current = None
        self.skip = 0
        self.scopes = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag in {"script", "style", "noscript"}:
            self.skip += 1
        if tag in {"li", "tr"} and not self.skip:
            self.scopes.append({"tag": tag, "start": len("".join(self.chunks))})
        href = attrs.get("href", "")
        if tag == "a" and not href and attrs.get("tagname", "").startswith("/"):
            # PBC pagination uses a literal path in both tagname and a reviewed
            # queryArticleByCondition call. Parse that path; execute no script.
            target = re.fullmatch(r"queryArticleByCondition\(this,\s*'([^']+)'\)", attrs.get("onclick", ""))
            if target and target[1] == attrs["tagname"]:
                href = target[1]
        if tag == "a" and not self.skip and href:
            self.current = {"href": href, "title_parts": [], "start": len("".join(self.chunks)),
                            "scope": self.scopes[-1] if self.scopes else None, "attribute_title": attrs.get("title", "")}
        if tag == "img" and self.current and attrs.get("alt"):
            self.current["title_parts"].append(attrs["alt"])
        if tag in {"li", "tr", "div", "p", "br"}:
            self.chunks.append("\n")

    def handle_endtag(self, tag):
        if tag in {"script", "style", "noscript"} and self.skip:
            self.skip -= 1
        if tag == "a" and self.current:
            self.current["end"] = len("".join(self.chunks))
            self.links.append(self.current)
            self.current = None
        if tag in {"li", "tr"} and self.scopes and self.scopes[-1]["tag"] == tag:
            self.scopes[-1]["end"] = len("".join(self.chunks))
            self.scopes.pop()

    def handle_data(self, data):
        if self.skip:
            return
        self.chunks.append(data)
        if self.current:
            self.current["title_parts"].append(data)


def extract_directory_links(raw_html, directory_url, cutoff_date):
    """Keep literal anchor titles/URLs and nearby directory dates; no numbers."""
    cutoff = cutoff_date if isinstance(cutoff_date, date) else date.fromisoformat(str(cutoff_date))
    parser = _Links()
    parser.feed(raw_html)
    text = "".join(parser.chunks)
    result = []
    for link in parser.links:
        raw_url = urljoin(directory_url, link["href"])
        url = _secure_locator(raw_url)
        if not _allowed(url):
            continue
        if url.rstrip("/") == directory_url.rstrip("/"):
            continue
        title = re.sub(r"\s+", " ", "".join(link["title_parts"]) or link["attribute_title"]).strip()
        if not title:
            continue
        # Dates after the anchor and before the next line are the most common
        # directory layout. Never borrow the next article's date.
        scope = link.get("scope")
        if scope and "end" in scope:
            after = text[link["end"]:scope["end"]][:150]
            before = text[scope["start"]:link["start"]][-100:]
            context = re.sub(r"\s+", " ", text[scope["start"]:scope["end"]]).strip()
        else:
            after = text[link["end"]:link["end"] + 120].split("\n", 1)[0]
            before = text[max(0, link["start"] - 60):link["start"]].split("\n")[-1]
            context = ""
        published = _date(after) or _date(before)
        basis = "directory_label" if published else ""
        if not published:
            match = re.search(r"(?:/|_|t)(20\d{2})(\d{2})(\d{2})(?=\d|_|/|\.)", url)
            if match:
                published = _date("-".join(match.groups()))
                basis = "publisher_url_date_discovery_hint"
        if published and published > cutoff:
            continue
        attachment = urlparse(url).path.lower().endswith((".pdf", ".xls", ".xlsx", ".csv", ".zip"))
        statistical_document = attachment or ("/attachDir/" in url and urlparse(url).path.lower().endswith((".htm", ".html")))
        # Year-only attachments can be discovered, but still have no admissible
        # publication date until their original page/data metadata is replayed.
        title_year = re.search(r"(20\d{2})", title)
        if title_year and int(title_year[1]) > cutoff.year:
            continue
        result.append({"url": url, "title": title, "published_at": published.isoformat() if published else "",
                       "publication_date_basis": basis, "directory_url": directory_url,
                       "directory_date_quote": (after if _date(after) else before) if basis == "directory_label" else "",
                       "attachment": attachment, "statistical_document": statistical_document,
                       "table_context_quote": context if statistical_document else "",
                       "original_href": link["href"], "transport_upgraded_to_https": raw_url != url,
                       "discovery_only": True})
    return result


def _family(request):
    cid = request.get("chart_id", "") or str(request.get("id", "")).split("::", 1)[0]
    domains = request.get("source_domains", [])
    for name, config in FAMILIES.items():
        if cid not in config["charts"]:
            continue
        if name == "nbs_macro_investment" and not (
                request.get("series_name") == "固定资产投资累计值"
                and request.get("unit") == "亿元" and request.get("frequency") == "monthly"
                and set(request.get("definition_aliases", [])) == {"固定资产投资"}
                and (not domains or any("stats.gov.cn" == domain for domain in domains))):
            continue
        if name == "nbs_auto_profit" and not any("stats.gov.cn" in domain for domain in domains):
            continue
        if name == "nbs_pmi" and domains and not any("stats.gov.cn" in domain for domain in domains):
            continue
        return name
    return ""


def _directory_urls(families, year):
    urls = []
    if any(name.startswith("nbs_") for name in families):
        # Publisher archive pagination, not a guessed release URL. The busier
        # release archive needs a wider window to include four GDP quarters.
        for base in ("https://www.stats.gov.cn/xxgk/sjfb/zxfb2020/", "https://www.stats.gov.cn/xxgk/jd/sjjd2020/"):
            count = (24 if "/sjfb/" in base else 15) if {"nbs_gdp", "nbs_gdp_demand"} & families else 6
            urls.extend([base + ("index.html" if number == 0 else f"index_{number}.html") for number in range(count)])
        if "nbs_gdp_demand" in families:
            # One reviewed national annual-bulletin directory. Its literal
            # anchor gives an explicit annual year for the Q4 demand release.
            urls.append("https://www.stats.gov.cn/xxgk/sjfb/tjgb2020/index.html")
    if any(name.startswith("pbc_") for name in families):
        urls.extend(["https://www.pbc.gov.cn/diaochatongjisi/116219/116225/index.html",
                     f"https://www.pbc.gov.cn/diaochatongjisi/116219/116319/{year}ntjsj/index.html"])
        if "pbc_lpr" in families:
            urls.append("https://www.pbc.gov.cn/zhengcehuobisi/125207/125213/125440/3876551/index.html")
    if "mof_fiscal" in families:
        urls.append("https://www.mof.gov.cn/zhengwuxinxi/redianzhuanti/quanguocaizhengshouzhiqingkuang/")
    return list(dict.fromkeys(urls))


def _matches(item, name):
    config = FAMILIES[name]
    host = urlparse(item["url"]).hostname or ""
    domain = "stats.gov.cn" if name.startswith("nbs_") else "pbc.gov.cn" if name.startswith("pbc_") else "mof.gov.cn"
    if not (host == domain or host.endswith("." + domain)):
        return False
    title = item["title"]
    if name == "nbs_gdp_demand" and _annual_bulletin_year(item):
        return True
    if name == "nbs_macro_investment":
        # Commentary/interview links can mention a period and GDP but need not
        # carry the reviewed main-indicators appendix. Require the actual
        # period-prefixed national-economy release, including June's reviewed
        # "上半年经济运行..." title which does not contain "国民经济".
        if any(word in title for word in ("解读", "答记者问", "记者", "统计师", "司长", "郑学工")):
            return False
        if not _macro_investment_period_hint(item):
            return False
    if config.get("required_keywords") and not any(word in title for word in config["required_keywords"]):
        return False
    if name == "pbc_finance" and any(word in title for word in ("地区", "区域", "各省", "地方")):
        return False
    if name == "pbc_lpr" and "报价行名单" in title:
        return False
    if config.get("quarterly_only") and not any(word in title for word in ("季度", "上半年", "全年", "郑学工")):
        return False
    return any(keyword.lower() in title.lower() for keyword in config["keywords"])


def _macro_investment_period_hint(item):
    """Only a title/directory-year locator hint, not an observation period.

    NBS monthly national-economy release titles omit the year. The directory
    publication year can disambiguate that locator (December published in
    January is the previous year). Original-table captions remain authoritative.
    """
    title = re.sub(r"\s+", "", item["title"])
    published = _date(item.get("published_at"))
    match = re.match(r"(?:(20\d{2})年)?((?:1[-—至])?(\d{1,2})月份?|上半年|前三季度|全年)", title)
    if not match or not published:
        return ""
    word = match[2]
    month = int(match[3]) if match[3] else {"上半年": 6, "前三季度": 9, "全年": 12}[word]
    if not 1 <= month <= 12:
        return ""
    year = int(match[1]) if match[1] else published.year - (1 if month == 12 and published.month <= 2 else 0)
    period = f"{year}-{month:02d}"
    if period > published.isoformat()[:7]:
        return ""
    return period


def _annual_bulletin_year(item):
    """Reviewed national-bulletin locator, not a provincial/thematic bulletin."""
    parsed = urlparse(item["url"])
    title = re.sub(r"\s+", "", item["title"])
    match = re.fullmatch(r"中华人民共和国(20\d{2})年国民经济和社会发展统计公报", title)
    if (not match or (parsed.hostname or "").lower() not in {"stats.gov.cn", "www.stats.gov.cn"}
            or parsed.scheme != "https"
            or not re.fullmatch(r"/xxgk/sjfb/tjgb2020/\d{6}/t20\d{6}_\d+\.html", parsed.path)):
        return ""
    directory = item.get("directory_url")
    if directory:
        location = urlparse(directory)
        if (location.scheme != "https" or (location.hostname or "").lower() not in {"stats.gov.cn", "www.stats.gov.cn"}
                or not re.fullmatch(r"/xxgk/sjfb/tjgb2020/index(?:_\d+)?\.html", location.path)):
            return ""
    return match[1]


def _period_hint(item, family=""):
    """Title period used ONLY to diversify locators, not actual data metadata."""
    if family == "nbs_macro_investment":
        return _macro_investment_period_hint(item)
    if family == "nbs_gdp_demand":
        year = _annual_bulletin_year(item)
        if year:
            return year + "-Q4"
    title = item["title"]
    year = re.search(r"(20\d{2})年", title)
    prefix = year[1] if year else ""
    month = re.search(r"(?:1\s*[-—至]\s*)?(\d{1,2})月", title) if year else None
    if month:
        return f"{prefix}-{int(month[1]):02d}"
    for words, quarter in ((("一季度", "第一季度"), 1), (("二季度", "第二季度", "上半年"), 2),
                           (("三季度", "第三季度", "前三季度"), 3), (("四季度", "第四季度", "全年"), 4)):
        if any(word in title for word in words):
            if not prefix:
                published = _date(item.get("published_at"))
                if not published:
                    return ""
                prefix = str(published.year - (1 if quarter == 4 and published.month <= 3 else 0))
            return f"{prefix}-Q{quarter}"
    if prefix and any(word in title for word in ("财政收支", "国内生产总值")):
        return f"{prefix}-Q4"
    return ""


def _preferred(item, family):
    title = item["title"]
    if family == "nbs_gdp_demand":
        # The annual bulletin names its statistical year explicitly; prefer it
        # to a January commentary whose title may say only "全年".
        return 2 if _annual_bulletin_year(item) else int("郑学工" in title)
    if family == "nbs_housing":
        return int("解读" in title)
    return int(not any(word in title for word in ("解读", "统计师", "司长")))


def _diversify(items, family):
    """Return recent distinct release periods before same-month commentaries."""
    grouped = {}
    for item in items:
        hint = _period_hint(item, family)
        if family == "nbs_gdp_demand" and not re.fullmatch(r"20\d{2}-Q[1-4]", hint):
            continue
        item = dict(item, discovery_period_hint=hint)
        grouped.setdefault(hint or _identity(item), []).append(item)
    first, extra = [], []
    for group in grouped.values():
        group.sort(key=lambda item: (_preferred(item, family), item["published_at"]), reverse=True)
        first.append(group[0])
        extra.extend(group[1:])
    if family == "nbs_gdp_demand":
        # Older annual bulletins cannot displace more recent quarter releases
        # merely because one was republished later. This sorts only locators.
        first.sort(key=lambda item: item["discovery_period_hint"], reverse=True)
    else:
        first.sort(key=lambda item: item["published_at"], reverse=True)
    extra.sort(key=lambda item: item["published_at"], reverse=True)
    limit = MAX_ITEMS_PER_FAMILY if family in {"nbs_gdp", "nbs_gdp_demand"} else 3
    return (first + extra)[:limit]


def _pbc_html_tables(request, documents):
    """Match reviewed original table captions, not the generic 'htm' anchor."""
    cid = request.get("chart_id", "") or str(request.get("id", "")).split("::", 1)[0]
    definition = str(request.get("definition", "")) + " " + str(request.get("series_name", ""))
    caption = ""
    if cid in {"s24-shape9", "s24-shape17"}:
        caption = "金融机构人民币信贷收支表"
    elif cid in {"s25-shape9", "s25-shape10"}:
        caption = "社会融资规模增量统计表"
    elif cid in {"s26-shape11", "s26-shape12"}:
        caption = "社会融资规模存量统计表" if "社会融资规模存量" in definition else "货币供应量"
    if not caption:
        return []
    result = []
    for item in documents:
        context = item.get("table_context_quote", "")
        if (not item.get("attachment") and item.get("statistical_document")
                and context.startswith(caption + " ")
                and urlparse(item["url"]).path.lower().endswith((".htm", ".html"))):
            result.append(dict(item, original_anchor_title=item["title"], title=context,
                               source_role="original_statistical_table_locator"))
    result.sort(key=lambda item: item["published_at"], reverse=True)
    return result[:1]


def _identity(item):
    path = urlparse(item["url"]).path
    name = path.rsplit("/", 1)[-1]
    # NBS repeats one release under its public and disclosure directories.
    return name if re.match(r"t20\d{6}_\d+\.html$", name) else item["url"]


async def discover_official_sources(requests, report_month, cutoff_date, cache_dir=None):
    """Return by-request directory locators and independently fetched receipts.

    ``cache_dir`` is caller-owned run storage. If supplied, raw HTML receipts are
    saved there; output metadata is not enough to prove an observation.
    """
    cutoff = cutoff_date if isinstance(cutoff_date, date) else date.fromisoformat(str(cutoff_date))
    if not re.fullmatch(r"20\d{2}-(0[1-9]|1[0-2])", str(report_month)):
        raise ValueError("invalid_report_month")
    family_by_request = {request["id"]: _family(request) for request in requests}
    families = set(family_by_request.values()) - {""}
    urls = _directory_urls(families, cutoff.year)
    semaphore = asyncio.Semaphore(3)
    root = Path(cache_dir).resolve() if cache_dir else None

    async def fetch(url):
        async with semaphore:
            try:
                try:
                    page = await _fetch_directory(url)
                except Exception as exc:
                    # Retry only a transient network timeout, never an invalid
                    # certificate/host or a parser/data error.
                    if not isinstance(exc, (TimeoutError, asyncio.TimeoutError)) and "timed out" not in str(exc).lower():
                        raise
                    page = await _fetch_directory(url)
                receipt = {key: page.get(key) for key in ("url", "requested_url", "raw_sha256", "fetched_at", "fetch_provider")}
                receipt.update({"status": "retrieved", "discovery_only": True})
                if root:
                    root.mkdir(parents=True, exist_ok=True)
                    path = root / (hashlib.sha256(url.encode()).hexdigest() + ".json")
                    temporary = path.with_suffix(".json.tmp")
                    temporary.write_text(json.dumps(page, ensure_ascii=False, indent=2), encoding="utf-8")
                    temporary.replace(path)
                    receipt["evidence_path"] = str(path)
                links = extract_directory_links(page["raw_html"], page["url"], cutoff)
                return receipt, links
            except Exception as exc:
                return {"url": url, "status": "retrieval_failed", "error_type": type(exc).__name__, "message": str(exc), "discovery_only": True}, []

    rows = await asyncio.gather(*(fetch(url) for url in urls))
    # Follow only publisher-provided annual statistical-category anchors. Their
    # contents are the PBC HTML/XLS/PDF counterparts, not a guessed attachment.
    child_urls = []
    for receipt, links in rows:
        if re.search(r"/116319/20\d{2}ntjsj/index\.html$", receipt["url"]):
            for item in links:
                if re.search(r"/116319/20\d{2}ntjsj/(shrzgm|hbtjgl|jrjgxdsztj)/index\.html$", item["url"]):
                    child_urls.append(item["url"])
    child_urls = list(dict.fromkeys(child_urls))
    rows.extend(await asyncio.gather(*(fetch(url) for url in child_urls)))
    directories = [item[0] for item in rows]
    all_links = [link for _, links in rows for link in links]
    family_items = {}
    attachments = []
    for name in families:
        matching = [item for item in all_links if _matches(item, name)]
        if name == "nbs_macro_investment":
            matching = [item for item in matching if _macro_investment_period_hint(item) <= str(report_month)]
        matching.sort(key=lambda item: item["published_at"], reverse=True)
        unique = {}
        for item in matching:
            unique.setdefault(_identity(item), item)
        family_items[name] = _diversify(list(unique.values()), name)
    # Annual PBC data directories label links only "PDF" or "Excel". Context
    # must be resolved on a separate original attachment fetch; no blind family
    # match or fictional publication date here.
    for item in all_links:
        if item["statistical_document"] and "pbc.gov.cn" in (urlparse(item["url"]).hostname or ""):
            attachments.append(item)
    attachments = list({item["url"]: item for item in attachments}.values())
    by_request = {}
    for request in requests:
        rid = request["id"]
        family = family_by_request[rid]
        originals = _pbc_html_tables(request, attachments) if family == "pbc_finance" else []
        items = originals + family_items.get(family, [])
        items = list({item["url"]: item for item in items}.values())
        by_request[rid] = {"family": family, "items": items,
                           "discovery_urls": [item["url"] for item in items],
                           "issues": [] if items else [{"code": "directory_no_matching_release" if family else "directory_family_not_supported"}]}
    return {"schema_version": SCHEMA_VERSION, "report_month": report_month, "cutoff_date": cutoff.isoformat(),
            "by_request": by_request,
            "directories": directories, "pbc_attachment_candidates": attachments, "discovery_only": True}
