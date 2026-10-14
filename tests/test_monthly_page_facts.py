"""Real quantity parsing and arithmetic; no model, network or browser calls."""
from __future__ import annotations

import json
import unittest
from copy import deepcopy
from pathlib import Path

from utils.monthly_page_facts import page_business_facts


MONTH = "2026-08"
REAL_PACKAGE = Path(__file__).resolve().parents[1] / "outputs/monthly-report-data/data-source-package-20261008-081855.json"


def table(code, entities, rows, axis="日期组合 (月)", percentages=()):
    lines = [code, *(["数量"] * len(entities)), axis, *entities]
    for period, values in rows.items():
        lines.extend([period, *(str(value) for value in values), *percentages])
    return {"code": code, "text": "\n".join(lines)}


def national(rows=None):
    return table("P1.1-1", ("整体市场",), rows or {"2025-08": [200], "2026-07": [90], MONTH: [100]})


def energy_month_table(rows=None):
    lines = ["P2-11.1", *(["数量"] * 4), *(["渗透率"] * 4),
             "2025", "2026", "2025", "2026", "2025", "2026", "2025", "2026",
             "月", "传统车", "传统车", "新能源", "新能源",
             "传统车", "传统车", "新能源", "新能源"]
    for month, values in (rows or {"07": [50, 30, 50, 60], "08": [90, 37, 110, 63]}).items():
        lines.extend([month, *(str(value) for value in values), "45.0%", "36.8%", "55.0%", "63.2%"])
    return {"code": "P2-11.1", "text": "\n".join(lines)}


def entity_table(code, rows, cumulative=False, periods=None):
    expected = periods or (["2025", "2026"] if cumulative else ["2025-07", "2025-08", "2026-07", MONTH])
    lines = [code, *(["数量"] * len(expected)), "企业简称", *expected]
    for name, values in rows.items():
        lines.extend([name, *(str(value) for value in values), "99.9%"])
    return {"code": code, "text": "\n".join(lines)}


def explicit_energy_metrics(cells, metric_headers=None):
    lines = ["P2-12.1", *(metric_headers or ["数量", "数量", "同比", "同比", "份额", "份额"]),
             "日期组合 (月)", *( ["插电式混合动力", "纯电动"] * 3)]
    for period, values in cells.items():
        lines.extend([period, *values])
    return {"code": "P2-12.1", "text": "\n".join(lines)}


def current(packet, entity, code, scope="single_month", month=MONTH):
    return next(row for row in packet["business_facts"] if row["entity"] == entity and
                row["source_card_code"] == code and row["scope"] == scope and row["period"] == month)


def group(packet, code, scope="single_month"):
    return next(row for row in packet["coverage"]["groups"] if row["card_code"] == code and row["scope"] == scope)


class MonthlyPageFactsParsingRegressionTest(unittest.TestCase):
    def test_current_prior_and_previous_quantities_determine_rates_not_percentages(self):
        cards = {"P1.1-1": national()}
        cards["P1.1-1"]["text"] += "\n-27.4%\n42.4%"
        packet = page_business_facts(4, cards, MONTH)
        row = current(packet, "整体市场", "P1.1-1")
        self.assertEqual((row["value"], row["comparison_value"], row["previous_value"]), (100, 200, 90))
        self.assertEqual((row["yoy_pct"], row["mom_pct"], row["delta_yoy"], row["delta_mom"]), (-50.0, 11.1, -100, 10))
        prior = current(packet, "整体市场", "P1.1-1", month="2025-08")
        self.assertNotIn("yoy_pct", prior)
        self.assertTrue(row["method"] and row["operands"] and row["source_fact_ids"])

    def test_dated_integer_without_quantity_header_is_not_assumed_to_be_sales(self):
        packet = page_business_facts(4, {"P1.1-1": {"text": "P1.1-1\n日期组合 (月)\n同比\n2026-08\n100"}}, MONTH)
        self.assertFalse(packet["business_facts"])
        self.assertFalse(group(packet, "P1.1-1")["complete"])

    def test_history_reference_finds_requested_month_in_a_later_view_without_actualizing_it(self):
        cards = {"P1.1-1": national(), "P1.1-2": {"text":
            "P1.1-2\n月\n历史月均字段\n01\n211.5\n---视图分段---\nP1.1-2\n月\n历史月均字段\n08\n173.8"}}
        row = current(page_business_facts(4, cards, MONTH), "历史月均", "P1.1-2", "history_reference")
        self.assertEqual((row["value"], row["unit"], row["metric"]), (173.8, "万辆", "reference_sales"))
        self.assertNotIn("yoy_pct", row)

    def test_conflicting_history_reference_is_excluded_not_duplicated(self):
        cards = {"P1.1-2": {"text": "P1.1-2\n月\n历史月均字段\n08\n173.8\n---视图分段---\nP1.1-2\n月\n历史月均字段\n08\n174.0"}}
        packet = page_business_facts(4, cards, MONTH)
        self.assertFalse(any(row["scope"] == "history_reference" for row in packet["business_facts"]))
        self.assertTrue(any(row["reason"] == "conflicting_history_reference" for row in packet["fact_warnings"]))

    def test_zero_baseline_is_a_real_zero_not_a_zero_growth_rate(self):
        packet = page_business_facts(4, {"P1.1-1": national({"2025-08": [0], MONTH: [100]})}, MONTH)
        row = current(packet, "整体市场", "P1.1-1")
        self.assertEqual((row["comparison_value"], row["delta_yoy"]), (0, 100))
        self.assertNotIn("yoy_pct", row)
        self.assertFalse(group(packet, "P1.1-1")["superlatives_by_metric"]["yoy_pct"])

    def test_equal_adjacent_percentages_do_not_shift_origin_entities(self):
        entities = ("自主", "美系", "欧系", "日系", "韩系")
        cards = {"P2-6.1": table("P2-6.1", entities,
                 {"2026-07": [1000, 100, 100, 100, 100], MONTH: [1039, 141, 102, 102, 82]},
                 percentages=("3.9%", "41.5%", "1.8%", "1.8%", "-18.4%"))}
        packet = page_business_facts(12, cards, MONTH)
        self.assertEqual(current(packet, "欧系", "P2-6.1")["mom_pct"], 2.0)
        self.assertEqual(current(packet, "日系", "P2-6.1")["mom_pct"], 2.0)
        self.assertEqual(current(packet, "韩系", "P2-6.1")["mom_pct"], -18.0)

    def test_inventory_scope_and_origin_c_d_are_not_sales_or_missing(self):
        cards = {"P1.1-1": national({"2026-07": [100], MONTH: [120]}),
                 "P1.2-1": table("P1.2-1", ("行业库存",), {"2026-07": [200], MONTH: [190]}, "库存日期"),
                 "P1.2-2A": table("P1.2-2A", ("新能源", "传统车"), {"2026-07": [80, 120], MONTH: [90, 100]}, "库存日期"),
                 "P1.2-2C": table("P1.2-2C", ("合资", "自主"), {"2026-07": [60, 140], MONTH: [50, 140]}, "库存日期"),
                 "P1.2-2B": table("P1.2-2B", ("新能源", "传统车"), {"07": [60, 40], "08": [80, 40]}, "月"),
                 "P1.2-2D": table("P1.2-2D", ("合资", "自主"), {"07": [40, 60], "08": [40, 80]}, "月")}
        packet = page_business_facts(5, cards, MONTH)
        nev = current(packet, "新能源", "P1.2-2A", "stock")
        self.assertEqual((nev["value"], nev["metric"], nev["mom_pct"]), (90, "inventory", 12.5))
        self.assertEqual(current(packet, "传统车", "P1.2-2A", "stock")["mom_pct"], -16.7)
        self.assertEqual(current(packet, "合资", "P1.2-2C", "stock")["value"], 50)
        self.assertEqual(current(packet, "自主", "P1.2-2D")["value"], 80)

    def test_bare_month_requires_independent_same_month_year_proof(self):
        cards = {"P1.2-2B": table("P1.2-2B", ("新能源", "传统车"), {"08": [80, 40]}, "月")}
        packet = page_business_facts(5, cards, MONTH)
        self.assertFalse(any(row["source_card_code"] == "P1.2-2B" for row in packet["business_facts"]))
        self.assertTrue(any(row["reason"] == "bare_month_year_not_verified" for row in packet["fact_warnings"]))

    def test_missing_middle_quantity_is_not_shifted_or_zero_filled(self):
        entities = ("10万以下", "10-15万", "15-20万", "20-25万", "25-35万", "35万以上")
        cards = {"P2-7.1": table("P2-7.1", entities, {"2026-07": [10, 20, 30, 40, 50, 60], MONTH: [10, 20, 40, 50, 60]})}
        packet = page_business_facts(13, cards, MONTH)
        self.assertFalse(any(row["period"] == MONTH and row["source_card_code"] == "P2-7.1" for row in packet["business_facts"]))
        self.assertFalse(group(packet, "P2-7.1")["complete"])
        self.assertTrue(any(row["reason"] == "incomplete_quantity_row" for row in packet["fact_warnings"]))

    def test_missing_comparison_universe_never_authorizes_superlatives(self):
        entities = ("轿车", "SUV", "MPV", "交叉型乘用车")
        cards = {"P2-1.1": table("P2-1.1", entities, {"2025-08": [20, 30, 10], MONTH: [20, 40, 10, 5]})}
        packet = page_business_facts(7, cards, MONTH)
        self.assertTrue(group(packet, "P2-1.1")["complete"])
        self.assertFalse(group(packet, "P2-1.1")["comparison_complete"])
        self.assertFalse(group(packet, "P2-1.1")["superlatives_by_metric"]["yoy_pct"])
        self.assertNotIn("yoy_pct", current(packet, "SUV", "P2-1.1"))

    def test_four_digit_quantity_is_not_an_unrelated_year_row(self):
        entities = ("自主", "美系", "欧系", "日系", "韩系")
        cards = {"P2-6.2": table("P2-6.2", entities, {"2025": [1000, 1500, 1800, 2100, 1900], "2026": [1001, 1501, 1801, 2101, 1901]}, "年")}
        packet = page_business_facts(12, cards, MONTH)
        self.assertEqual(current(packet, "日系", "P2-6.2", "year_to_date")["value"], 2101)

    def test_conflicting_complete_viewports_remove_ambiguous_target_row(self):
        entities = ("A00", "A0", "A", "B", "C+")
        left = table("P2-2.1", entities, {MONTH: [20, 40, 80, 100, 60]})
        right = table("P2-2.1", entities, {MONTH: [20, 40, 81, 100, 60]})
        left["text"] += "\n---视图分段---\n" + right["text"]
        packet = page_business_facts(8, {"P2-2.1": left}, MONTH)
        self.assertFalse(any(row["period"] == MONTH for row in packet["business_facts"]))
        self.assertTrue(any(row["reason"] == "conflicting_complete_rows" for row in packet["fact_warnings"]))

    def test_energy_year_and_entity_headers_keep_nev_separate_from_conventional(self):
        packet = page_business_facts(17, {"P2-11.1": energy_month_table()}, MONTH)
        nev = current(packet, "新能源", "P2-11.1")
        conventional = current(packet, "传统车", "P2-11.1")
        self.assertEqual((nev["value"], nev["comparison_value"], nev["share_pct"]), (63, 110, 63.0))
        self.assertEqual((conventional["value"], conventional["share_pct"]), (37, 37.0))

    def test_incomplete_year_energy_row_is_not_reinterpreted_as_two_values(self):
        packet = page_business_facts(17, {"P2-11.1": energy_month_table({"08": [90, 37, 110]})}, MONTH)
        self.assertFalse(packet["business_facts"])
        self.assertTrue(any(row["reason"] == "incomplete_year_energy_row" for row in packet["fact_warnings"]))

    def test_bev_phev_market_denominators_are_distinct_and_no_fuel_cell_is_invented(self):
        cards = {"P1.1-1": national(), "P2-11.1": energy_month_table(),
                 "P2-12.1": table("P2-12.1", ("插电式混合动力", "纯电动"),
                                  {"2025-08": [40, 70], "2026-07": [20, 40], MONTH: [21, 42]})}
        packet = page_business_facts(18, cards, MONTH)
        internal = current(packet, "BEV", "P2-12.1")
        overall = current(packet, "BEV", "P2-12.2")
        self.assertEqual((internal["share_scope"], internal["share_pct"]), ("nev_market", 66.7))
        self.assertEqual((overall["share_scope"], overall["share_pct"]), ("passenger_market", 42.0))
        self.assertFalse(any(row["entity"] == "燃料电池" for row in packet["business_facts"]))
        self.assertFalse(group(packet, "P2-12.2")["complete"])
        self.assertIn("P1.1-1:整体市场:single_month:2025-08", overall["source_fact_ids"])

    def test_missing_nev_total_only_permits_explicit_bev_phev_subset_share(self):
        cards = {"P2-12.1": table("P2-12.1", ("插电式混合动力", "纯电动"), {MONTH: [20, 80]})}
        packet = page_business_facts(18, cards, MONTH)
        self.assertEqual(current(packet, "BEV", "P2-12.1")["share_scope"], "bev_phev_market")
        self.assertNotIn("share_pct", current(packet, "BEV", "P2-12.2"))

    def test_direct_bi_yoy_requires_complete_named_header_and_all_six_cells(self):
        card = explicit_energy_metrics({"2026-07": ["294683", "630772", "-19.7%", "2.3%", "31.8%", "68.2%"],
                                        MONTH: ["294418", "687983", "-25.3%", "-3.2%", "30.0%", "70.0%"]})
        packet = page_business_facts(18, {"P2-12.1": card}, MONTH)
        row = current(packet, "BEV", "P2-12.1", month="2026-07")
        self.assertEqual((row["yoy_pct"], row["observed_yoy_pct"], row["source_method"]), (2.3, 2.3, "direct BI percent cell"))
        self.assertNotIn("comparison_value", row)
        self.assertEqual((row["percent_operands"]["index"], row["percent_operands"]["raw_cell"]), (3, "2.3%"))
        self.assertEqual(len(row["percent_operands"]["raw_cells"]), 6)

    def test_direct_bi_yoy_rejects_missing_percent_or_wrong_metric_header(self):
        for card in (
            explicit_energy_metrics({MONTH: ["20", "80", "2.3%", "20.0%", "80.0%"]}),
            explicit_energy_metrics({MONTH: ["20", "80", "1.0%", "2.3%", "20.0%", "80.0%"]},
                                    ["数量", "数量", "环比", "环比", "份额", "份额"]),
        ):
            with self.subTest(text=card["text"]):
                row = current(page_business_facts(18, {"P2-12.1": card}, MONTH), "BEV", "P2-12.1")
                self.assertNotIn("yoy_pct", row)
                self.assertNotIn("observed_yoy_pct", row)
                self.assertNotIn("comparison_value", row)

    def test_direct_bi_rate_never_overwrites_conflicting_quantity_arithmetic(self):
        card = explicit_energy_metrics({"2025-08": ["40", "60", "40.0%", "60.0%"],
                                        MONTH: ["20", "80", "-50.0%", "2.3%", "20.0%", "80.0%"]})
        packet = page_business_facts(18, {"P2-12.1": card}, MONTH)
        row = current(packet, "BEV", "P2-12.1")
        self.assertEqual((row["comparison_value"], row["yoy_pct"]), (60, 33.3))
        self.assertNotIn("observed_yoy_pct", row)
        self.assertTrue(any(warning["reason"] == "direct_percentage_disagrees_with_quantity_derivation" for warning in packet["fact_warnings"]))

    def test_region_year_table_requires_monthly_national_total_not_ytd_assumption(self):
        region = entity_table("P2-8.2", {"东部": [100, 50], "中部": [40, 20], "西部": [45, 25], "东北": [15, 5]}, True)
        region["text"] = region["text"].replace("企业简称", "区域-使用")
        packet = page_business_facts(14, {"P1.1-1": national(), "P2-8.2": region}, MONTH)
        row = current(packet, "东部", "P2-8.2")
        self.assertEqual((row["scope"], row["period"], row["share_pct"]), ("single_month", MONTH, 50.0))
        broken = deepcopy(region)
        broken["text"] = broken["text"].replace("\n50\n", "\n51\n", 1)
        rejected = page_business_facts(14, {"P1.1-1": national(), "P2-8.2": broken}, MONTH)
        self.assertFalse(any(row["source_card_code"] == "P2-8.2" for row in rejected["business_facts"]))
        self.assertTrue(any(row["reason"] == "year_table_not_verified_as_target_month" for row in rejected["fact_warnings"]))

    def test_enterprise_missing_cell_does_not_consume_the_following_entity(self):
        card = entity_table("P2-10.1", {"缺列企业": [10, 20, 30], "完整企业": [40, 50, 60, 70]})
        packet = page_business_facts(16, {"P1.1-1": national(), "P2-10.1": card}, MONTH)
        self.assertFalse(any(row["entity"] == "缺列企业" for row in packet["business_facts"]))
        complete = current(packet, "完整企业", "P2-10.1")
        self.assertEqual((complete["value"], complete["comparison_value"], complete["previous_value"]), (70, 50, 60))
        self.assertEqual(complete["rank_in_observed"], 1)
        self.assertNotIn("rank", complete)
        self.assertFalse(group(packet, "P2-10.1")["complete"])

    def test_enterprise_date_header_must_match_requested_four_periods(self):
        card = entity_table("P2-10.1", {"错期企业": [10, 20, 30, 40]}, periods=["2025-07", "2025-08", MONTH, "2026-07"])
        packet = page_business_facts(16, {"P2-10.1": card}, MONTH)
        self.assertFalse(packet["business_facts"])
        self.assertFalse(group(packet, "P2-10.1")["complete"])

    def test_enterprise_subset_is_not_used_as_market_share_denominator(self):
        card = entity_table("P2-10.1", {"甲企业": [10, 20, 30, 40], "乙企业": [20, 30, 40, 50]})
        packet = page_business_facts(16, {"P2-10.1": card}, MONTH)
        self.assertNotIn("share_pct", current(packet, "甲企业", "P2-10.1"))
        self.assertNotIn("share_pct", current(packet, "乙企业", "P2-10.1"))
        self.assertFalse(group(packet, "P2-10.1")["complete"])

    def test_future_month_facts_use_new_dates_and_signs(self):
        entities = ("一线城市", "新一线城市", "二线城市", "三线城市", "四线城市", "五线城市")
        card = table("P2-9.1", entities, {"2025-09": [10, 20, 30, 40, 50, 60], MONTH: [20, 30, 40, 50, 60, 70], "2026-09": [30, 40, 50, 60, 70, 80]})
        packet = page_business_facts(15, {"P2-9.1": card}, "2026-09")
        row = current(packet, "一线城市", "P2-9.1", month="2026-09")
        self.assertEqual((row["yoy_pct"], row["mom_pct"]), (200.0, 50.0))
        self.assertIn("2026-09", row["fact_id"])


@unittest.skipUnless(REAL_PACKAGE.is_file(), "captured private 45-card package is not available")
class MonthlyPageFactsRealPackageTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        package = json.loads(REAL_PACKAGE.read_text(encoding="utf-8"))
        if (package["cards_expected"], package["cards_captured"], package["cards_usable"]) != (45, 45, 45):
            raise AssertionError("real data fixture is no longer a complete 45-card package")
        cls.cards = {card["code"]: card for card in package["cards"]}

    def packet(self, page):
        before = deepcopy(self.cards)
        packet = page_business_facts(page, self.cards, MONTH)
        self.assertEqual(self.cards, before)
        rows = packet["business_facts"]
        self.assertEqual(len({row["fact_id"] for row in rows}), len(rows))
        self.assertTrue(packet["coverage"]["has_target_period_facts"])
        for row in rows:
            self.assertEqual(row["fact_id"], f"{row['source_card_code']}:{row['entity']}:{row['scope']}:{row['period']}")
            self.assertTrue(row["method"] and row["operands"] and row["source_fact_ids"])
        return packet

    def test_page_4_retail_ytd_reference_and_february_scope(self):
        packet = self.packet(4)
        row = current(packet, "整体市场", "P1.1-1")
        self.assertEqual((row["value"], row["yoy_pct"], row["mom_pct"]), (1555628, -22.5, 4.8))
        self.assertEqual(current(packet, "整体市场", "P1.1-1", month="2026-02")["yoy_pct"], -14.0)
        self.assertNotIn("yoy_pct", current(packet, "整体市场", "P1.1-1", month="2025-02"))
        self.assertEqual(current(packet, "整体市场", "P1.1-3", "year_to_date")["value"], 11838788)
        self.assertEqual(current(packet, "历史月均", "P1.1-2", "history_reference")["value"], 173.8)

    def test_page_5_inventory_increase_and_origin_groups(self):
        packet = self.packet(5)
        self.assertEqual(current(packet, "行业库存", "P1.2-1", "stock")["value"], 4119751)
        self.assertEqual(current(packet, "新能源", "P1.2-2A", "stock")["mom_pct"], 1.5)
        self.assertEqual(current(packet, "合资", "P1.2-2C", "stock")["value"], 1481230)
        self.assertEqual(current(packet, "自主", "P1.2-2D")["value"], 1083713)
        self.assertEqual(current(packet, "新能源", "P1.2-2B")["value"], 982401)

    def test_page_7_category_month_and_ytd_shares(self):
        packet = self.packet(7)
        suv = current(packet, "SUV", "P2-1.1")
        self.assertEqual((suv["value"], suv["share_pct"], suv["previous_share_pct"]), (849107, 54.6, 55.1))
        self.assertEqual(current(packet, "交叉型乘用车", "P2-1.1")["previous_value"], 8594)
        self.assertEqual(current(packet, "SUV", "P2-1.2", "year_to_date")["share_pct"], 54.1)

    def test_page_8_level_signs_and_comparison_month(self):
        packet = self.packet(8)
        self.assertEqual(current(packet, "C+", "P2-2.1")["mom_pct"], -3.1)
        self.assertEqual(current(packet, "C+", "P2-2.1", month="2026-07")["mom_pct"], -7.2)
        self.assertEqual(current(packet, "A0", "P2-2.1")["yoy_pct"], 2.0)
        self.assertEqual(current(packet, "B", "P2-2.2", "year_to_date")["share_pct"], 38.4)

    def test_page_12_origin_yoy_mom_and_month_vs_ytd(self):
        packet = self.packet(12)
        japanese = current(packet, "日系", "P2-6.1")
        self.assertEqual((japanese["value"], japanese["mom_pct"], japanese["yoy_pct"]), (167042, 1.8, -34.8))
        self.assertEqual(current(packet, "韩系", "P2-6.1")["mom_pct"], -18.4)
        self.assertEqual(current(packet, "自主", "P2-6.1")["share_pct"], 69.7)
        self.assertEqual(current(packet, "自主", "P2-6.2", "year_to_date")["share_pct"], 64.7)

    def test_page_13_prices_recover_full_quantity_columns(self):
        packet = self.packet(13)
        self.assertEqual(current(packet, "15-20万", "P2-7.1")["mom_pct"], -1.0)
        self.assertEqual(current(packet, "35万以上", "P2-7.1")["mom_pct"], -6.0)
        self.assertEqual(current(packet, "20-25万", "P2-7.1")["mom_pct"], 14.2)
        self.assertEqual(current(packet, "25-35万", "P2-7.2", "year_to_date")["share_pct"], 15.4)

    def test_page_14_regions_are_monthly_and_pp_uses_unrounded_ratios(self):
        packet = self.packet(14)
        east = current(packet, "东部", "P2-8.2")
        self.assertEqual((east["value"], east["yoy_pct"], east["share_pct"]), (790969, -21.1, 50.8))
        self.assertEqual(current(packet, "中部", "P2-8.2")["share_change_pp"], -1.2)
        self.assertEqual(current(packet, "西部", "P2-8.2")["share_change_pp"], 0.6)
        self.assertEqual(current(packet, "江苏", "P2-8.1")["yoy_pct"], -13.3)
        self.assertFalse(group(packet, "P2-8.1")["complete"])

    def test_page_15_city_lines_month_and_cumulative(self):
        packet = self.packet(15)
        self.assertEqual(current(packet, "一线城市", "P2-9.1")["mom_pct"], 0.2)
        self.assertEqual(current(packet, "三线城市", "P2-9.1")["mom_pct"], 6.5)
        self.assertEqual(current(packet, "一线城市", "P2-9.2", "year_to_date")["share_pct"], 10.6)

    def test_page_16_chery_actual_current_sales_and_byd_share(self):
        packet = self.packet(16)
        chery = current(packet, "奇瑞汽车", "P2-10.1")
        self.assertEqual((chery["value"], chery["mom_pct"]), (83422, 9.8))
        self.assertEqual(current(packet, "比亚迪汽车", "P2-10.1")["share_pct"], 14.9)
        self.assertEqual(current(packet, "长安汽车", "P2-10.1")["share_pct"], 5.6)
        self.assertFalse(group(packet, "P2-10.1")["superlatives_allowed"])

    def test_page_17_nev_is_63_2_not_the_conventional_36_8(self):
        packet = self.packet(17)
        row = current(packet, "新能源", "P2-11.1")
        self.assertEqual((row["value"], row["share_pct"], row["yoy_pct"]), (982401, 63.2, -11.1))
        self.assertEqual(current(packet, "传统车", "P2-11.1")["yoy_pct"], -36.5)
        self.assertEqual(current(packet, "新能源", "P2-11.2", "year_to_date")["share_pct"], 54.6)

    def test_page_18_bev_and_phev_two_denominators(self):
        packet = self.packet(18)
        row = current(packet, "BEV", "P2-12.1")
        self.assertEqual((row["value"], row["yoy_pct"], row["share_pct"]), (687983, -3.2, 70.0))
        self.assertEqual(current(packet, "BEV", "P2-12.2")["share_pct"], 44.2)
        self.assertEqual(current(packet, "PHEV", "P2-12.2")["share_pct"], 18.9)
        self.assertEqual(current(packet, "BEV", "P2-12.3", "year_to_date")["share_pct"], 68.0)
        self.assertFalse(any(row["entity"] == "燃料电池" for row in packet["business_facts"]))
        july = current(packet, "BEV", "P2-12.1", month="2026-07")
        self.assertEqual((july["yoy_pct"], july["source_method"]), (2.3, "direct BI percent cell"))
        self.assertNotIn("comparison_value", july)

    def test_page_19_changan_declines_and_leapmotor_has_not_overtaken_ytd(self):
        packet = self.packet(19)
        changan = current(packet, "长安汽车", "P2-13.1")
        self.assertEqual((changan["value"], changan["mom_pct"]), (56647, -4.2))
        self.assertEqual(current(packet, "比亚迪汽车", "P2-13.1")["share_pct"], 23.6)
        leapmotor = current(packet, "零跑汽车", "P2-13.2", "year_to_date")
        changan_ytd = current(packet, "长安汽车", "P2-13.2", "year_to_date")
        self.assertLess(leapmotor["value"], changan_ytd["value"])
        self.assertEqual((changan_ytd["rank_in_observed"], leapmotor["rank_in_observed"]), (3, 4))


if __name__ == "__main__":
    unittest.main()
