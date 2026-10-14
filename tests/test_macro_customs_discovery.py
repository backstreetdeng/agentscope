from datetime import date
import hashlib
import importlib.util
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

PATH = Path(__file__).resolve().parents[1] / "skills/macro-monthly-report/scripts/macro_customs_discovery.py"
SPEC = importlib.util.spec_from_file_location("customs_discovery_test_module", PATH)
d = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(d)


def url(number):
    return f"http://english.customs.gov.cn/Statics/{number:08d}-1111-2222-3333-444444444444.html"


def request(name):
    return {"id": "s19-shape13::" + name, "chart_id": "s19-shape13", "series_name": name,
            "definition": "美元计价进出口：" + name, "unit": d.SERIES[name][0],
            "frequency": "monthly", "source_domains": ["customs.gov.cn"]}


def directory(family, links, year=2026, extra=""):
    title = d.DIRECTORY_TITLES[family]
    return (f'<select id="{d.SELECTORS[family]}"><option value="{year}">{year}</option>'
            f'<option value="2025">2025</option></select><table><tr><td>{title}</td><td>'
            + "".join(f'<a href="{href}">{label}.</a>' for label, href in links)
            + "</td></tr>" + extra + "</table>")


def article(family, day, periods=("2026-06", "2026-07", "2026-08"), locator="2026-08"):
    if family == "customs_monthly_balance":
        title = "1.Summary of Imports and Exports (In USD) B：Monthly"
        table = ('<table><tr><td colspan="9">' + title + '</td></tr>'
                 '<tr><td colspan="9">Unit:US$ million</td></tr>'
                 '<tr><td>Year&amp;Month</td><td>Total</td><td>Export</td><td>Import</td><td>Balance</td><td>1to8</td></tr>'
                 '<tr><td>Total</td><td>Export</td><td>Import</td><td>Balance</td></tr>'
                 + "".join('<tr><td>' + period.replace("-", ".") + '</td>' + '<td>123</td>' * 8 + '</tr>' for period in periods)
                 + '</table>')
    else:
        year, month = locator.split("-")
        title = f"(2) China's Total Export &amp; Import Values by Trade Mode, {d.MONTHS[int(month)-1]} {year} (in USD)"
        table = ('<table><tr><td>' + title + '</td></tr><tr><td>Unit: USD1 Million</td></tr>'
                 '<tr><td>Trade Mode</td></tr><tr><td>Total</td></tr><tr><td>123</td></tr></table>')
    return (f'<div class="atcl"><div class="atcl-main"><div class="atcl-ttl">{title}</div></div>'
            f'<div class="atcl-layout"><div class="atcl-date">{day}</div><div class="atcl-cnt">{table}</div></div></div>')


def receipt(location, raw):
    digest = hashlib.sha256(raw.encode()).hexdigest()
    return {"url": location, "requested_url": location, "raw_html": raw, "raw_sha256": digest,
            "html_sha256": digest, "fetch_provider": "test-only-offline", "fetched_at": "2026-10-04T00:00:00Z"}


class UrlAndDomTests(unittest.TestCase):
    def test_exact_url_boundary(self):
        self.assertTrue(d._allowed(url(1), "article"))
        self.assertTrue(d._allowed(url(1).replace("http:", "https:"), "article"))
        for value in [url(1) + "?", url(1) + "#", url(1) + "?x=1", url(1) + "#x",
                      url(1).replace("english.customs.gov.cn", "english.customs.gov.cn.evil"),
                      url(1).replace("english.customs.gov.cn", "evil.customs.gov.cn"),
                      url(1).replace("english.customs.gov.cn", "u:p@english.customs.gov.cn"),
                      url(1).replace("english.customs.gov.cn", "english.customs.gov.cn:8931"),
                      url(1).replace("/Statics/", "/Statics/../Statics/"),
                      url(1).replace("/Statics/", "/%53tatics/"), url(1).replace("http:", ""),
                      url(1).replace("http://", "http:\\\\"), url(1) + "\n"]:
            with self.subTest(value=value):
                self.assertFalse(d._allowed(value))

    def test_only_one_exact_usd_row_and_literal_year(self):
        family = "customs_trade_yoy"
        raw = directory(family, [("Jun", url(6))], extra='<tr><td>(2)China\'sTotalExport&amp;ImportValuesbyTradeMode(inCNY)</td><td><a href="'+url(9)+'">Jun.</a></td></tr>')
        items = d.extract_customs_directory(raw, d.DIRECTORIES[family], family, 2026)
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["discovery_period_hint"], "2026-06")
        self.assertEqual(items[0]["published_at"], "")
        with self.assertRaisesRegex(ValueError, "year_not_requested"):
            d.extract_customs_directory(raw, d.DIRECTORIES[family], family, 2025)
        duplicated = raw.replace("</table>", raw[raw.index("<table>")+7:raw.index("</table>")] + "</table>")
        with self.assertRaisesRegex(ValueError, "usd_row_ambiguous"):
            d.extract_customs_directory(duplicated, d.DIRECTORIES[family], family, 2026)

    def test_duplicate_month_even_same_url_rejected(self):
        raw = directory("customs_trade_yoy", [("Jun", url(6)), ("Jun", url(6))])
        with self.assertRaisesRegex(ValueError, "month_ambiguous"):
            d.extract_customs_directory(raw, d.DIRECTORIES["customs_trade_yoy"], "customs_trade_yoy", 2026)

    def test_directory_cannot_change_family_or_escape(self):
        for href in ["//english.customs.gov.cn/Statics/00000006-1111-2222-3333-444444444444.html",
                     "https://evil.example/x", "/statics/report/monthly.html"]:
            with self.assertRaisesRegex(ValueError, "article_url_not_allowed"):
                d.extract_customs_directory(directory("customs_trade_yoy", [("Jun", href)]), d.DIRECTORIES["customs_trade_yoy"], "customs_trade_yoy", 2026)
        with self.assertRaisesRegex(ValueError, "family_mismatch"):
            d.extract_customs_directory(directory("customs_trade_yoy", []), d.DIRECTORIES["customs_monthly_balance"], "customs_trade_yoy", 2026)

    def test_article_date_real_dom_not_script_navigation_or_locator(self):
        raw = article("customs_monthly_balance", "2026/09/18")
        wrapped = '<nav>Date 2025-01-01</nav><script>const fake="<div class=\"atcl-date\">2027/01/01</div>"</script>' + raw
        result = d.extract_customs_article(wrapped, url(8), "customs_monthly_balance", "2026-08")
        self.assertEqual(result["published_at"], "2026-09-18")
        self.assertEqual(result["publication_date_basis"], "reviewed_customs_atcl_date_dom")
        self.assertEqual(result["available_periods"], ["2026-06", "2026-07", "2026-08"])
        with self.assertRaisesRegex(ValueError, "publication_date_missing"):
            d.extract_customs_article(raw.replace("2026/09/18", "Sep 2026"), url(8), "customs_monthly_balance", "2026-08")

    def test_duplicate_dates_outside_article_cannot_supply_missing_header(self):
        raw = article("customs_monthly_balance", "2026/09/18")
        with self.assertRaisesRegex(ValueError, "components_ambiguous"):
            d.extract_customs_article(raw.replace('<div class="atcl-date">', '<div class="atcl-date">2026/09/19</div><div class="atcl-date">'), url(8), "customs_monthly_balance", "2026-08")
        with self.assertRaisesRegex(ValueError, "components_ambiguous"):
            d.extract_customs_article(raw.replace('class="atcl-date"', 'class="unrelated"') + '<div class="atcl-date">2026/09/18</div>', url(8), "customs_monthly_balance", "2026-08")

    def test_hidden_components_do_not_escape_with_stray_endtag(self):
        raw = article("customs_monthly_balance", "2026/09/18")
        for tag in ("template", "noscript"):
            with self.assertRaisesRegex(ValueError, "scope_ambiguous"):
                d.extract_customs_article(f"<{tag}></bogus>" + raw + f"</{tag}>", url(8), "customs_monthly_balance", "2026-08")

    def test_table_outside_content_and_cny_annual_rejected(self):
        raw = article("customs_monthly_balance", "2026/09/18")
        for altered in [raw.replace('class="atcl-cnt"', 'class="unrelated"'), raw.replace("In USD", "In CNY"), raw.replace("B：Monthly", "A：Annually")]:
            with self.assertRaises(ValueError):
                d.extract_customs_article(altered, url(8), "customs_monthly_balance", "2026-08")
        with self.assertRaisesRegex(ValueError, "period_or_scope_changed"):
            d.extract_customs_article(article("customs_trade_yoy", "2026/09/09", locator="2026-08"), url(8), "customs_trade_yoy", "2026-07")

    def test_dns_private_and_redirect_scope_fail_closed(self):
        with patch.object(d.socket, "getaddrinfo", return_value=[(2, 1, 6, "", ("127.0.0.1", 80))]):
            with self.assertRaisesRegex(ValueError, "not_public"):
                d._public(url(1))
        with patch.object(d, "_public"):
            req = d.Request(d.DIRECTORIES["customs_trade_yoy"])
            with self.assertRaisesRegex(ValueError, "redirect_path_changed"):
                d._Redirect().redirect_request(req, None, 302, "", {}, d.DIRECTORIES["customs_monthly_balance"])


class SelectionTests(unittest.IsolatedAsyncioTestCase):
    async def run_discovery(self, balance_days=("2026/07/22", "2026/08/18", "2026/09/18"), latest_periods=("2026-06", "2026-07", "2026-08"), fail=None, cache_dir=None, broken_table=None):
        docs = {
            d.DIRECTORIES["customs_trade_yoy"]: directory("customs_trade_yoy", [("Jun", url(16)), ("Jul", url(17)), ("Aug", url(18))]),
            d.DIRECTORIES["customs_monthly_balance"]: directory("customs_monthly_balance", [("Jun", url(6)), ("Jul", url(7)), ("Aug", url(8))]),
        }
        for n, day in zip((6, 7, 8), balance_days):
            docs[url(n)] = article("customs_monthly_balance", day, latest_periods if n == 8 else ("2026-06", "2026-07", "2026-08"))
            if n == broken_table:
                docs[url(n)] = docs[url(n)].replace("Unit:US$ million", "Unknown old layout")
        for n, day in ((16, "2026/07/15"), (17, "2026/08/10"), (18, "2026/09/09")):
            docs[url(n)] = article("customs_trade_yoy", day, locator=f"2026-{n-10:02d}")
        async def fetch(location):
            if location == fail:
                raise TimeoutError("actual offline timeout case")
            return receipt(location, docs[location])
        requests = [request(name) for name in d.SERIES]
        with patch.object(d, "_fetch", side_effect=fetch):
            return await d.discover_customs_sources(requests, "2026-09", "2026-10-03", cache_dir)

    async def test_latest_balance_one_receipt_revisions_not_candidates(self):
        result = await self.run_discovery()
        balance = result["by_request"][request("贸易差额(亿美元)")["id"]]
        self.assertEqual(balance["discovery_urls"], [url(8)])
        self.assertEqual(balance["required_periods"], ["2026-06", "2026-07", "2026-08"])
        self.assertEqual(len(result["balance_revision_receipts"]), 3)
        self.assertTrue(balance["source_restrictions"]["disallow_generic_search_history_mix"])
        for name in ("出口金额:当月同比(%,右轴)", "进口金额:当月同比(%,右轴)"):
            self.assertEqual(result["by_request"][request(name)["id"]]["discovery_urls"], [url(16), url(17), url(18)])
        self.assertFalse(any("value" in item for item in balance["items"]))

    async def test_actual_publication_not_directory_month_determines_latest(self):
        result = await self.run_discovery(balance_days=("2026/09/25", "2026/09/26", "2026/09/18"))
        self.assertEqual(result["balance_selection_proof"]["selected_url"], url(7))
        result = await self.run_discovery(balance_days=("2026/07/22", "2026/08/18", "2026/10/04"))
        self.assertEqual(result["balance_selection_proof"]["selected_url"], url(7))

    async def test_latest_missing_history_never_falls_back_to_complete_old(self):
        result = await self.run_discovery(latest_periods=("2026-08",))
        self.assertEqual(result["balance_selection_proof"]["selected_url"], url(8))
        self.assertEqual(result["by_request"][request("贸易差额(亿美元)")["id"]]["items"], [])
        self.assertIn("customs_latest_balance_history_incomplete", [item["code"] for item in result["issues"]])

    async def test_unread_header_prevents_claiming_latest(self):
        result = await self.run_discovery(fail=url(6))
        self.assertEqual(result["by_request"][request("贸易差额(亿美元)")["id"]]["items"], [])
        self.assertIn("customs_latest_balance_version_unproven", [item["code"] for item in result["issues"]])

    async def test_equal_latest_date_ambiguous_no_arbitrary_tiebreak(self):
        result = await self.run_discovery(balance_days=("2026/07/22", "2026/09/18", "2026/09/18"))
        self.assertEqual(result["by_request"][request("贸易差额(亿美元)")["id"]]["items"], [])
        self.assertIn("customs_latest_balance_version_ambiguous", [item["code"] for item in result["issues"]])

    async def test_older_unsupported_table_valid_header_does_not_block_latest(self):
        result = await self.run_discovery(broken_table=6)
        self.assertEqual(result["by_request"][request("贸易差额(亿美元)")["id"]]["discovery_urls"], [url(8)])
        self.assertEqual(result["issues"], [])
        revision = next(row for row in result["balance_revision_receipts"] if row["url"] == url(6))
        self.assertEqual(revision["table_parse_status"], "rejected")

    async def test_latest_unsupported_table_never_falls_back(self):
        result = await self.run_discovery(broken_table=8)
        self.assertEqual(result["balance_selection_proof"]["selected_url"], url(8))
        self.assertEqual(result["by_request"][request("贸易差额(亿美元)")["id"]]["items"], [])
        self.assertIn("customs_latest_balance_table_unproven", [item["code"] for item in result["issues"]])

    async def test_cache_is_raw_receipt_only_and_unsupported_request_no_fetch(self):
        with TemporaryDirectory() as root:
            result = await self.run_discovery(cache_dir=root)
            self.assertEqual(len(list(Path(root).glob("*.json"))), 8)
            self.assertTrue(result["discovery_only"])
        wrong = request("贸易差额(亿美元)")
        wrong["unit"] = "亿元人民币"
        with patch.object(d, "_fetch") as fetch:
            result = await d.discover_customs_sources([wrong], "2026-09", "2026-10-03")
            fetch.assert_not_called()
            self.assertEqual(result["by_request"][wrong["id"]]["items"], [])


if __name__ == "__main__":
    unittest.main()
