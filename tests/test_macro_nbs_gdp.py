"""Synthetic fixtures test mechanics; live public receipt replay is separate."""
import copy
from datetime import date
from hashlib import sha256
import importlib.util
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1] / "skills/macro-monthly-report/scripts"


def load(name):
    spec = importlib.util.spec_from_file_location("gdp_test_" + name, ROOT / (name + ".py"))
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    return module


gdp = load("macro_nbs_gdp")
source = load("macro_sources")
contract = load("macro_contract")
CUTOFF = date(2026, 10, 3)


def requests():
    charts = [{"id": cid, "categories": ["2025-Q3", "2025-Q4", "2026-Q1", "2026-Q2"],
               "series": [{"name": name, "values": [None] * 4} for name in names]}
              for cid, names in (("s10-shape7", ("GDP平减指数", "GDP:不变价:当季同比")),
                                 ("s10-shape28", ("消费支出拉动", "资本形成拉动", "货物和服务净出口拉动", "GDP:累计同比")))]
    return [r for chart in charts for r in contract.request_contract(chart)]


def page(raw, url="https://www.stats.gov.cn/sj/zxfb/202607/t20260716_1964142.html"):
    p = source.parse_page(raw, url)
    p.update(receipt_id="synthetic-gdp", text_sha256=sha256(p["text"].encode()).hexdigest(),
             fetch_provider="direct-public-publisher")
    return p


def quarter_tables():
    raw = '<html><title>2026年二季度和上半年国内生产总值初步核算结果</title><p>2026/07/16 09:30</p>'
    raw += '<p>表1　2026年二季度和上半年GDP初步核算数据</p><table>'
    raw += '<tr><td rowspan="2"></td><td colspan="2">绝对额（亿元）</td><td colspan="2">比上年同期增长（%）</td></tr>'
    raw += '<tr><td>二季度</td><td>上半年</td><td>二季度</td><td>上半年</td></tr>'
    raw += '<tr><td>GDP</td><td>361511</td><td>695704</td><td>4.3</td><td>4.7</td></tr>'
    raw += '<tr><td colspan="5">注：绝对额按现价计算，增长速度按不变价计算；</td></tr></table>'
    raw += '<p>表2　GDP同比增长速度</p><table><tr><td colspan="5">单位：%</td></tr>'
    raw += '<tr><td>年份</td><td>1季度</td><td>2季度</td><td>3季度</td><td>4季度</td></tr>'
    raw += '<tr><td>2025</td><td>5.4</td><td>5.2</td><td>4.8</td><td>4.5</td></tr>'
    raw += '<tr><td>2026</td><td>5.0</td><td>4.3</td><td></td><td></td></tr>'
    raw += '<tr><td colspan="5">注：同比增长速度为与上年同期对比的增长速度。</td></tr></table></html>'
    return page(raw)


def cumulative_prose(quarter=2, year=2026):
    marker = {1: "一季度", 2: "上半年", 3: "前三季度"}[quarter]
    month = quarter * 3 + 1
    pub = f"{year}/{month:02d}/16"
    raw = f'<html><title>郑学工：{marker}经济运行总体平稳</title><p>{pub} 10:00</p>'
    raw += f'<p>{marker}，我国国内生产总值（GDP）为695704亿元，按不变价格计算，同比增长4.7%。</p>'
    for label, points, qpoints in (("最终消费支出", "2.1", "1.9"), ("资本形成总额", "1.7", "1.5"), ("货物和服务净出口", "0.8", "0.9")):
        raw += f'<p>{marker}，{label}拉动GDP增长{points}个百分点。其中，二季度{label}拉动GDP增长{qpoints}个百分点。</p>'
    raw += '</html>'
    return page(raw, f"https://www.stats.gov.cn/sj/zxfbhjd/{year}{month:02d}/t{year}{month:02d}16_1964139.html")


def annual_prose():
    raw = '<html><p>中华人民共和国2025年国民经济和社会发展统计公报[1]</p><p>2026年2月28日</p>'
    raw += '<p>初步核算，全年国内生产总值[2]1401879亿元，比上年增长5.0%。'
    raw += '最终消费支出拉动国内生产总值增长2.6个百分点，资本形成总额拉动国内生产总值增长0.8个百分点，货物和服务净出口拉动国内生产总值增长1.6个百分点。'
    raw += '分季度看，一季度国内生产总值同比增长5.4%，二季度增长5.2%，三季度增长4.8%，四季度增长4.5%。</p>'
    raw += '<p>[2]国内生产总值、三次产业及相关行业增加值绝对数按现价计算，增长速度按不变价格计算。</p></html>'
    return page(raw, "https://www.stats.gov.cn/xxgk/sjfb/tjgb2020/202602/t20260228_1962662.html")


def changed_text(p, old, new):
    p = copy.deepcopy(p); p["text"] = p["text"].replace(old, new)
    p["text_sha256"] = sha256(p["text"].encode()).hexdigest()
    return p


class NbsGdpTests(unittest.TestCase):
    def candidate(self, p=None, rid="s10-shape28::消费支出拉动"):
        p = p or cumulative_prose(); r = next(r for r in requests() if r["id"] == rid)
        c = next(c for c in gdp.reviewed_gdp_candidates(p, [r]))
        return r, c, p

    def test_real_contract_five_supported_roles_and_deflator_is_not_guessed(self):
        self.assertEqual(len(requests()), 6)
        candidates = gdp.reviewed_gdp_candidates(quarter_tables(), requests())
        self.assertEqual({(c["request_id"], c["period"]) for c in candidates},
                         {("s10-shape7::GDP:不变价:当季同比", p) for p in ("2025-Q3", "2025-Q4", "2026-Q1", "2026-Q2")}
                         | {("s10-shape28::GDP:累计同比", "2026-Q2")})
        self.assertNotIn("s10-shape7::GDP平减指数", {c["request_id"] for c in candidates})

    def test_same_vintage_four_quarter_cells_and_cumulative_column_are_distinct(self):
        p = quarter_tables(); by_id = {r["id"]: r for r in requests()}
        cs = gdp.reviewed_gdp_candidates(p, requests())
        values = {(c["request_id"], c["period"]): c["value"] for c in cs}
        self.assertEqual(values[("s10-shape7::GDP:不变价:当季同比", "2026-Q2")], 4.3)
        self.assertEqual(values[("s10-shape28::GDP:累计同比", "2026-Q2")], 4.7)
        for c in cs:
            v = gdp.verify_gdp_candidate(c, by_id[c["request_id"]], p, CUTOFF, "2026-09")
            self.assertTrue(v["reviewed_period_and_definition"])
            self.assertNotIn("derived_value_verified", v)

    def test_main_table_physical_growth_column_and_original_hash_replayed(self):
        r, c, p = self.candidate(quarter_tables(), "s10-shape28::GDP:累计同比")
        self.assertEqual(c["nbs_gdp_proof"]["column_index"], 4)
        c["value"] = 695704; c["value_text"] = "695704"
        with self.assertRaises(ValueError): gdp.verify_gdp_candidate(c, r, p, CUTOFF, "2026-09")
        p["tables"][0]["html_sha256"] = "invented"
        self.assertNotIn("s10-shape28::GDP:累计同比", {x["request_id"] for x in gdp.reviewed_gdp_candidates(p, [r])})

    def test_history_cannot_be_cumulative_mom_or_nominal(self):
        for old, new in (("表2　GDP同比增长速度", "表2　GDP累计增长速度"),
                         ("比上年同期增长（%）", "比上期增长（%）"),
                         ("不变价", "现价")):
            p = quarter_tables()
            for t in p["tables"]:
                t["source_html"] = t["source_html"].replace(old, new)
                t["html_sha256"] = sha256(t["source_html"].encode()).hexdigest()
            p = changed_text(p, old, new)
            for t in p["tables"]: t["context"] = t["context"].replace(old, new)
            if old == "表2　GDP同比增长速度":
                self.assertFalse(any(c["nbs_gdp_proof"]["mode"] == "gdp_quarter_history_table" for c in gdp.reviewed_gdp_candidates(p, requests())))
            else:
                self.assertFalse(any(c["nbs_gdp_proof"]["mode"] == "gdp_main_table" for c in gdp.reviewed_gdp_candidates(p, requests())))

    def test_cumulative_direct_points_not_quarter_points(self):
        cs = gdp.reviewed_gdp_candidates(cumulative_prose(), requests())
        values = {c["request_id"]: c["value"] for c in cs}
        self.assertEqual(values["s10-shape28::消费支出拉动"], 2.1)
        self.assertEqual(values["s10-shape28::资本形成拉动"], 1.7)
        self.assertEqual(values["s10-shape28::货物和服务净出口拉动"], 0.8)
        self.assertEqual(values["s10-shape28::GDP:累计同比"], 4.7)

    def test_contribution_rate_is_never_substituted_or_multiplied(self):
        p = changed_text(cumulative_prose(), "最终消费支出拉动GDP增长2.1个百分点", "最终消费支出对经济增长贡献率为44.7%")
        cs = gdp.reviewed_gdp_candidates(p, requests())
        self.assertEqual({c["request_id"] for c in cs}, {"s10-shape28::GDP:累计同比"})

    def test_explicit_contribution_rate_in_sentence_keeps_only_literal_points(self):
        p = changed_text(cumulative_prose(), "最终消费支出拉动GDP增长2.1个百分点", "最终消费支出对经济增长贡献率为44.7%，拉动GDP增长2.1个百分点")
        r, c, _ = self.candidate(p)
        self.assertEqual(c["value"], 2.1); self.assertNotEqual(c["value"], 44.7)
        gdp.verify_gdp_candidate(c, r, p, CUTOFF, "2026-09")

    def test_same_period_identity_with_rounding_tolerance_no_value_adjustment(self):
        p = cumulative_prose(); r, c, _ = self.candidate(p)
        self.assertEqual(sum(item["value"] for item in c["nbs_gdp_proof"]["cumulative_demand_identity"]), 4.6)
        self.assertEqual(c["nbs_gdp_proof"]["cumulative_gdp_value"], 4.7)
        altered = changed_text(p, "资本形成总额拉动GDP增长1.7个百分点", "资本形成总额拉动GDP增长2.7个百分点")
        self.assertEqual(gdp.reviewed_gdp_candidates(altered, requests()), [])
        with self.assertRaises(ValueError): gdp.verify_gdp_candidate(c, r, altered, CUTOFF, "2026-09")

    def test_quarterly_demand_cannot_fill_cumulative_roles(self):
        p = changed_text(cumulative_prose(), "上半年，最终消费支出", "二季度，最终消费支出")
        self.assertFalse(any(c["unit"] == "百分点" for c in gdp.reviewed_gdp_candidates(p, requests())))

    def test_annual_explicit_year_gdp_price_note_and_direct_points(self):
        p = annual_prose(); cs = gdp.reviewed_gdp_candidates(p, requests())
        self.assertEqual(len(cs), 4); self.assertEqual({c["period"] for c in cs}, {"2025-Q4"})
        self.assertEqual({c["value"] for c in cs}, {5.0, 2.6, 0.8, 1.6})
        for c in cs:
            r = next(r for r in requests() if r["id"] == c["request_id"])
            gdp.verify_gdp_candidate(c, r, p, CUTOFF, "2026-09")
        self.assertEqual(gdp.reviewed_gdp_candidates(changed_text(p, "中华人民共和国2025年", "中华人民共和国2026年"), requests()), [])

    def test_publication_dates_are_literal_not_fetched_dates(self):
        p = cumulative_prose(); p["published_at"] = "2026-08-16"
        self.assertEqual(gdp.reviewed_gdp_candidates(p, requests()), [])

    def test_forecast_and_prior_year_prefix_are_not_hidden_by_sentence_matching(self):
        for prefix in ("预计", "预测", "2025年"):
            p = changed_text(cumulative_prose(), "上半年，我国国内生产总值", prefix + "上半年，我国国内生产总值")
            self.assertEqual(gdp.reviewed_gdp_candidates(p, requests()), [])
            p = changed_text(cumulative_prose(), "上半年，最终消费支出", prefix + "上半年，最终消费支出")
            self.assertFalse(any(c["unit"] == "百分点" for c in gdp.reviewed_gdp_candidates(p, requests())))
        p = changed_text(cumulative_prose(), "郑学工：上半年经济运行总体平稳", "郑学工：2025年上半年经济运行总体平稳")
        self.assertEqual(gdp.reviewed_gdp_candidates(p, requests()), [])
        p = cumulative_prose(); p["fetched_at"] = "2030-01-01"
        self.assertEqual({c["period"] for c in gdp.reviewed_gdp_candidates(p, requests())}, {"2026-Q2"})
        p = changed_text(cumulative_prose(), "2026/07/16", "2026/07/17")
        self.assertEqual(gdp.reviewed_gdp_candidates(p, requests()), [])

    def test_publication_cutoff_and_quarter_end_target_checked_again(self):
        r, c, p = self.candidate()
        with self.assertRaisesRegex(ValueError, "after_cutoff"): gdp.verify_gdp_candidate(c, r, p, date(2026, 7, 15), "2026-09")
        with self.assertRaisesRegex(ValueError, "after_publication_or_target"): gdp.verify_gdp_candidate(c, r, p, CUTOFF, "2026-05")

    def test_relative_prior_year_prefix_rejected_not_yoy_comparison_in_capture(self):
        for prefix in ("去年", "上年", "前年"):
            p = changed_text(cumulative_prose(), "上半年，我国国内生产总值", prefix + "上半年，我国国内生产总值")
            self.assertEqual(gdp.reviewed_gdp_candidates(p, requests()), [])
            p = changed_text(cumulative_prose(quarter=1), "一季度，最终消费支出", prefix + "一季度，最终消费支出")
            self.assertFalse(any(c["unit"] == "百分点" for c in gdp.reviewed_gdp_candidates(p, requests())))
        # This phrase is inside the captured actual annual observation, not a year qualifier before it.
        cs = gdp.reviewed_gdp_candidates(annual_prose(), requests())
        self.assertEqual(len(cs), 4)
        self.assertTrue(any("比上年增长" in c["quote"] for c in cs if c["request_id"] == "s10-shape28::GDP:累计同比"))

    def test_every_field_proof_and_arbitrary_flag_independently_replayed(self):
        r, original, p = self.candidate()
        for key in original:
            if key == "nbs_gdp_proof": continue
            c = copy.deepcopy(original); c[key] = "invented"
            with self.assertRaises((ValueError, TypeError)): gdp.verify_gdp_candidate(c, r, p, CUTOFF, "2026-09")
        for key in original["nbs_gdp_proof"]:
            c = copy.deepcopy(original); c["nbs_gdp_proof"][key] = "invented"
            with self.assertRaises((ValueError, TypeError, AttributeError)): gdp.verify_gdp_candidate(c, r, p, CUTOFF, "2026-09")
        c = copy.deepcopy(original); c["derived_value_verified"] = True
        with self.assertRaises(ValueError): gdp.verify_gdp_candidate(c, r, p, CUTOFF, "2026-09")

    def test_core_output_metadata_white_list_checks_every_original_field(self):
        r, c, p = self.candidate()
        metadata = {"series_name": r["series_name"], "receipt_id": p["receipt_id"], "source_url": p["url"],
                    "published_at": p["published_at"], "source_grade": "primary", "publisher_id": "primary:www.stats.gov.cn"}
        output = {**c, **metadata}
        self.assertEqual(gdp.verify_gdp_candidate(c, r, p, CUTOFF, "2026-09"), gdp.verify_gdp_candidate(output, r, p, CUTOFF, "2026-09"))
        for key in metadata:
            altered = {**output, key: "invented"}
            with self.assertRaisesRegex(ValueError, "provenance_changed"): gdp.verify_gdp_candidate(altered, r, p, CUTOFF, "2026-09")

    def test_no_regional_consultation_yearbook_or_unsupported_page(self):
        for url in ("https://regional.stats.gov.cn/sj/zxfbhjd/202607/t20260716_1964139.html",
                    "https://www.stats.gov.cn/hd/lyzx/202607/t20260716_1964139.html"):
            p = cumulative_prose(); p["url"] = url
            self.assertEqual(gdp.reviewed_gdp_candidates(p, requests()), [])
        for p in ({}, {"text": ""}, {**cumulative_prose(), "text_sha256": "invented"}):
            self.assertEqual(gdp.reviewed_gdp_candidates(p, requests()), [])

    def test_duplicates_only_identical_quotes_do_not_create_history_or_conflicts(self):
        p = cumulative_prose(); p["text"] += "\n" + p["text"]
        p["text_sha256"] = sha256(p["text"].encode()).hexdigest()
        self.assertEqual(len(gdp.reviewed_gdp_candidates(p, requests())), 4)
        p = changed_text(p, "其中，二季度最终消费支出拉动GDP增长1.9个百分点。", "上半年，最终消费支出拉动GDP增长3.1个百分点。")
        self.assertFalse(any(c["unit"] == "百分点" for c in gdp.reviewed_gdp_candidates(p, requests())))

    def test_unreviewed_unit_definition_scope_and_coordinates_are_rejected(self):
        r, c, p = self.candidate()
        for key, value in (("definition", "三大需求当季贡献率"), ("unit", "%"), ("frequency", "monthly")):
            altered = {**r, key: value}
            self.assertEqual(gdp.reviewed_gdp_candidates(p, [altered]), [])
            with self.assertRaises(ValueError): gdp.verify_gdp_candidate(c, altered, p, CUTOFF, "2026-09")
        r, c, p = self.candidate(quarter_tables(), "s10-shape28::GDP:累计同比")
        c["nbs_gdp_proof"]["table_index"] = False
        with self.assertRaisesRegex(ValueError, "coordinates_invalid"): gdp.verify_gdp_candidate(c, r, p, CUTOFF, "2026-09")


class NbsGdpCoreTests(unittest.TestCase):
    """Execute after root attaches the independently verified helper branch."""
    def test_core_table_and_prose_candidates_output_replay(self):
        by_id = {r["id"]: r for r in requests()}
        for p in (quarter_tables(), cumulative_prose(), annual_prose()):
            for c in gdp.reviewed_gdp_candidates(p, requests()):
                output = source.validate_observation(c, by_id[c["request_id"]], p, CUTOFF, "2026-09")
                replay = source.validate_observation(output, by_id[c["request_id"]], p, CUTOFF, "2026-09")
                self.assertEqual(output, replay); self.assertEqual(output["nbs_gdp_proof"], c["nbs_gdp_proof"])
                self.assertEqual(output["observation_kind"], "actual")

    def test_core_cannot_relabel_rate_as_points_or_change_growth_cell(self):
        p = cumulative_prose(); by_id = {r["id"]: r for r in requests()}
        c = next(c for c in gdp.reviewed_gdp_candidates(p, requests()) if c["request_id"] == "s10-shape28::消费支出拉动")
        output = source.validate_observation(c, by_id[c["request_id"]], p, CUTOFF, "2026-09")
        for key, value in (("value", 44.7), ("unit", "%"), ("period", "2026-Q1"), ("observation_kind", "derived")):
            altered = {**output, key: value}
            with self.assertRaises(ValueError): source.validate_observation(altered, by_id[c["request_id"]], p, CUTOFF, "2026-09")

    def test_core_reviewed_yoy_group_does_not_bypass_other_scope_or_point_role(self):
        by_id = {r["id"]: r for r in requests()}
        p = quarter_tables()
        c = next(c for c in gdp.reviewed_gdp_candidates(p, requests())
                 if c["request_id"] == "s10-shape7::GDP:不变价:当季同比" and c["period"] == "2026-Q2")
        r = copy.deepcopy(by_id[c["request_id"]]); r["context_groups"].append(["环比", "month-on-month"])
        with self.assertRaisesRegex(ValueError, "context_scope_unproven"):
            source.validate_observation(c, r, p, CUTOFF, "2026-09")
        p = annual_prose()
        c = next(c for c in gdp.reviewed_gdp_candidates(p, requests()) if c["request_id"] == "s10-shape28::消费支出拉动")
        r = copy.deepcopy(by_id[c["request_id"]]); r["context_groups"].append(["同比", "year-on-year"])
        with self.assertRaisesRegex(ValueError, "context_scope_unproven"):
            source.validate_observation(c, r, p, CUTOFF, "2026-09")
        p = quarter_tables()
        c = next(c for c in gdp.reviewed_gdp_candidates(p, requests()) if c["request_id"] == "s10-shape28::GDP:累计同比")
        c.pop("nbs_gdp_proof")
        with self.assertRaises(ValueError): source.validate_observation(c, by_id[c["request_id"]], p, CUTOFF, "2026-09")


if __name__ == "__main__":
    unittest.main()
