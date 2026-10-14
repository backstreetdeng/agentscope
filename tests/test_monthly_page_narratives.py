"""Real 12-page drafts plus counterexamples for the typed business gate.

Models, browsers and external services are never called. Counterfactual months
are explicitly local test scenarios, not reported business measurements.
"""
from __future__ import annotations

import json
import re
import unittest
from copy import deepcopy
from pathlib import Path

from utils.monthly_page_facts import page_business_facts
from utils.monthly_page_narratives import BUSINESS_PAGES, business_fact_draft, overview_business_packet, validate_business_slide, _width
from utils.monthly_report_narrative import PAGE_LABELS, _ppt_narrative_text


MONTH = "2026-08"
PACKAGE = Path(__file__).resolve().parents[1] / "outputs/monthly-report-data/data-source-package-20261008-081855.json"


def _record(packet, entity, code, scope="single_month"):
    return next(row for row in packet["business_facts"] if row["entity"] == entity and
                row["source_card_code"] == code and row["scope"] == scope and row["period"] == MONTH)


def _claim(role, text, *rows):
    return {"role": role, "claim": text, "fact_ids": [row["fact_id"] for row in rows],
            "evidence_ids": [], "certainty": "unverified"}


def _slide(page, claims):
    return {"slide": page, "headline": "目标月份对象与不同口径走势应分别观察", "headline_evidence_ids": [],
            "anomaly": {"type": "structural_divergence", "priority": 7,
                        "fact_ids": list(dict.fromkeys(value for claim in claims for value in claim["fact_ids"]))},
            "body_claims": claims}


@unittest.skipUnless(PACKAGE.is_file(), "captured private 45-card package is not available")
class MonthlyBusinessNarrativeRegressionTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        package = json.loads(PACKAGE.read_text(encoding="utf-8"))
        cls.cards = {card["code"]: card for card in package["cards"]}

    def packet(self, page):
        packet = page_business_facts(page, self.cards, MONTH)
        packet["required_prefix"] = PAGE_LABELS[page]
        return packet

    def assert_real_draft(self, page):
        packet = self.packet(page)
        draft = business_fact_draft(page, packet, MONTH)
        validate_business_slide(draft, packet)
        self.assertTrue(draft["business_validation"]["entity_metric_scope_checked"])
        self.assertEqual({claim["role"] for claim in draft["body_claims"]}, {"core", "structure", "support"})
        body = "；".join(claim["claim"].rstrip("；。 ") for claim in draft["body_claims"])
        self.assertGreaterEqual(_width(body), 120)
        self.assertLessEqual(_width(body), 150)
        _, rendered = _ppt_narrative_text(draft, MONTH)
        if page == 5:
            self.assertEqual(rendered,'')  # Claims remain private; template has no body.
            return
        for claim in draft["body_claims"]:
            # Wrapping may split a clause, but cannot discard a supporting layer.
            self.assertIn(claim["claim"].rstrip("；。 "), rendered.replace("\n", ""))

    def test_real_page_4_draft(self): self.assert_real_draft(4)
    def test_real_page_5_draft(self): self.assert_real_draft(5)
    def test_real_page_7_draft(self): self.assert_real_draft(7)
    def test_real_page_8_draft(self): self.assert_real_draft(8)
    def test_real_page_12_draft(self): self.assert_real_draft(12)
    def test_real_page_13_draft(self): self.assert_real_draft(13)
    def test_real_page_14_draft(self): self.assert_real_draft(14)
    def test_real_page_15_draft(self): self.assert_real_draft(15)
    def test_real_page_16_draft(self): self.assert_real_draft(16)
    def test_real_page_17_draft(self): self.assert_real_draft(17)
    def test_real_page_18_draft(self): self.assert_real_draft(18)
    def test_real_page_19_draft(self): self.assert_real_draft(19)

    def fixture(self, page):
        """A stable, dense valid fixture isolates semantics from draft editing."""
        packet = self.packet(page)
        business_fact_draft(page, packet, MONTH)  # Register genuine local CALC facts/guards.
        row = lambda entity, code, scope="single_month": _record(packet, entity, code, scope)
        if page == 17:
            nev, trad, ytd = row("新能源", "P2-11.1"), row("传统车", "P2-11.1"), row("新能源", "P2-11.2", "year_to_date")
            claims = [
                _claim("core", "8月新能源单月零售98.2万辆，同比下降11.1%、环比增长6.2%，传统车同比下降36.5%，两种能源表现应区分观察。", nev, trad),
                _claim("structure", "新能源占整体市场63.2%，较上月提高0.8个百分点，份额改善与销量同比下降同时存在，不宜据此判断需求方向。", nev, trad),
                _claim("support", "1—8月新能源累计零售646.4万辆、同比下降12.6%，累计与单月采用不同口径，份额不能代替规模变化。", ytd),
            ]
        elif page == 5:
            total, sale = row("行业库存", "P1.2-1", "stock"), row("整体市场", "P1.1-1")
            nev, trad = row("新能源", "P1.2-2A", "stock"), row("传统车", "P1.2-2A", "stock")
            nr = next(value for value in packet["business_facts"] if value["entity"] == "新能源" and "inventory_sales_ratio" in value)
            tr = next(value for value in packet["business_facts"] if value["entity"] == "传统车" and "inventory_sales_ratio" in value)
            claims = [
                _claim("core", "8月行业库存412.0万辆、环比下降2.0%，整体市场单月零售155.6万辆、环比增长4.8%，库存与销量分化。", total, sale),
                _claim("structure", "新能源库存202.5万辆、环比增长1.5%，传统车库存209.5万辆、环比下降5.1%，去化节奏分化，不能概括为同步下降。", nev, trad),
                _claim("support", "传统车存销比3.7，新能源存销比2.1，库存负担与去化速度需分别判断，不能把总量下降泛化为各能源同步下降。", tr, nr),
            ]
        elif page == 12:
            own, jp, us, kr = (row(entity, "P2-6.1") for entity in ("自主", "日系", "美系", "韩系"))
            oy, jy = row("自主", "P2-6.2", "year_to_date"), row("日系", "P2-6.2", "year_to_date")
            claims = [
                _claim("core", "8月自主单月零售108.4万辆，同比下降17.3%，日系同比下降34.8%，两者降幅不同，份额优势不能代替销量增长。", own, jp),
                _claim("structure", "美系环比增长41.5%，日系环比增长1.8%，韩系环比下降18.4%，不同系别增速不能互借，需同时关注比较基期。", us, jp, kr),
                _claim("support", "自主累计份额64.7%、同比下降17.2%，日系累计份额12.6%、同比下降21.2%，累计与单月采用各自口径。", oy, jy),
            ]
        elif page == 8:
            a0, a, b, c = (row(entity, "P2-2.1") for entity in ("A0", "A", "B", "C+"))
            gain = next(value for value in packet["business_facts"] if value["entity"] == "B与A0" and value["metric"] == "delta_mom")
            contribution = next(value for value in packet["business_facts"] if value["entity"] == "B与A0" and value["metric"] == "net_change_share_pct")
            claims = [
                _claim("core", "8月A0级单月同比增长2.0%，A级同比下降31.5%，B级同比下降20.8%，级别表现不同，不能泛化到全市场。", a0, a, b),
                _claim("structure", f"B与A0合计环比净增{gain['delta_mom']/10000:.1f}万辆，占全级别环比净增{contribution['net_change_share_pct']:.1f}%；B级单月份额38.0%，增量贡献与增速排序不同。", gain, contribution, b),
                _claim("support", "C+级单月零售24.1万辆、环比下降3.1%，与A0级环比增长14.1%方向不同；同比、环比和份额基期不同，不可混用。", c, a0),
            ]
        elif page == 18:
            bev, phev, overall = row("BEV", "P2-12.1"), row("PHEV", "P2-12.1"), row("BEV", "P2-12.2")
            claims = [
                _claim("core", "8月BEV单月零售68.8万辆、同比下降3.2%，PHEV同比下降25.3%，两种动力同比表现不同，应区分规模与增速。", bev, phev),
                _claim("structure", "BEV占新能源内部70.0%，BEV占整体市场44.2%，两项份额的分母不同，不能用内部份额替代整体市场份额。", bev, overall),
                _claim("support", "BEV环比增长9.1%，PHEV环比下降0.1%，同比收缩与环比恢复并不一致，需按两种动力和不同基期分别观察。", bev, phev),
            ]
        elif page == 16:
            byd, geely, chery, ca = (row(entity, "P2-10.1") for entity in ("比亚迪汽车", "吉利汽车", "奇瑞汽车", "长安汽车"))
            yb, yg = row("比亚迪汽车", "P2-10.2", "year_to_date"), row("吉利汽车", "P2-10.2", "year_to_date")
            claims = [
                _claim("core", "8月比亚迪汽车单月零售23.2万辆、同比下降23.5%，吉利汽车同比下降20.6%，两家增速不同，不用规模代替增长方向。", byd, geely),
                _claim("structure", "奇瑞汽车环比增长9.8%，长安汽车环比下降1.6%，企业恢复节奏不同，头部样本走势不能概括所有企业。", chery, ca),
                _claim("support", "比亚迪汽车累计同比下降32.5%，吉利汽车累计同比下降13.2%，单月回升和累计规模变化应采用各自的比较口径。", yb, yg),
            ]
        else:
            raise AssertionError(f"no stable fixture for page {page}")
        draft = _slide(page, claims)
        validate_business_slide(draft, packet)
        return draft, packet

    def assert_semantic_rejection(self, slide, packet):
        with self.assertRaises(ValueError) as rejected:
            validate_business_slide(slide, packet)
        self.assertNotRegex(str(rejected.exception), r"正文显示宽度|三层事实关系")

    def test_nev_cannot_borrow_conventional_36_8_share(self):
        draft, packet = self.fixture(17)
        draft["body_claims"][1]["claim"] = draft["body_claims"][1]["claim"].replace("63.2%", "36.8%")
        self.assert_semantic_rejection(draft, packet)

    def test_unqualified_share_after_semicolon_cannot_borrow_other_entity_value(self):
        draft, packet = self.fixture(17)
        draft["body_claims"][1]["claim"] = "新能源占整体市场63.2%；占整体市场36.8%，份额改善与销量同比下降同时存在，不宜据此判断需求方向。"
        self.assert_semantic_rejection(draft, packet)

    def test_unqualified_share_after_full_stop_cannot_borrow_other_entity_value(self):
        draft, packet = self.fixture(17)
        draft["body_claims"][1]["claim"] = "新能源占整体市场63.2%。占整体市场36.8%，份额改善与销量同比下降同时存在，不宜据此判断需求方向。"
        self.assert_semantic_rejection(draft, packet)

    def test_unqualified_rate_after_semicolon_cannot_reverse_preceding_entity_direction(self):
        draft, packet = self.fixture(17)
        draft["body_claims"][1]["claim"] = "新能源占整体市场63.2%；环比下降6.2%，份额改善与销量同比下降同时存在，不宜据此判断需求方向。"
        self.assert_semantic_rejection(draft, packet)

    def test_measurement_before_first_named_entity_cannot_borrow_a_cited_value(self):
        draft, packet = self.fixture(17)
        draft["body_claims"][1]["claim"] = "占整体市场36.8%；新能源占整体市场63.2%，份额改善与销量同比下降同时存在，不宜据此判断需求方向。"
        self.assert_semantic_rejection(draft, packet)

    def test_unknown_share_grammar_cannot_bypass_numeric_entity_pairing(self):
        draft, packet = self.fixture(17)
        draft["body_claims"][1]["claim"] = "新能源销量占全国零售市场36.8%，较上月提高0.8个百分点，份额改善与销量同比下降同时存在，不宜判断需求方向。"
        self.assert_semantic_rejection(draft, packet)

    def test_three_generic_roles_and_exact_ids_do_not_replace_verified_fact_layers(self):
        draft, packet = self.fixture(17)
        draft["headline"] = "新能源结构应与市场走势结合观察"
        generic = [
            "新能源市场表现应结合销量和结构分别观察，注意比较口径与目标月份的关系，避免简单判断。",
            "传统车与新能源的结构变化应对照销售节奏，区分同比和环比的不同基期，不依赖单个指标解释行业走势。",
            "新能源累计表现应与单月事实分别核对，数据用于识别结构变化，经营判断应观察不同指标的关系。",
        ]
        for claim, text in zip(draft["body_claims"], generic):
            claim["claim"] = text
        body = "；".join(claim["claim"].rstrip("；。 ") for claim in draft["body_claims"])
        self.assertEqual(_width(body), 132)
        self.assertEqual({claim["role"] for claim in draft["body_claims"]}, {"core", "structure", "support"})
        self.assertTrue(all(claim["fact_ids"] for claim in draft["body_claims"]))
        with self.assertRaises(ValueError) as rejected:
            validate_business_slide(draft, packet)
        self.assertNotIn("正文显示宽度", str(rejected.exception))

    def test_nev_share_change_uses_raw_ratio_rounding_not_rounded_share_subtraction(self):
        draft, packet = self.fixture(17)
        nev = _record(packet, "新能源", "P2-11.1")
        self.assertEqual(nev["share_change_pp"], 0.8)
        draft["body_claims"][1]["claim"] = draft["body_claims"][1]["claim"].replace("提高0.8", "提高0.9")
        self.assert_semantic_rejection(draft, packet)

    def test_share_change_cannot_swap_previous_month_for_prior_year(self):
        draft, packet = self.fixture(17)
        self.assertEqual(_record(packet, "新能源", "P2-11.1")["share_comparison_scope"], "previous_month")
        draft["body_claims"][1]["claim"] = draft["body_claims"][1]["claim"].replace("较上月", "较去年同期")
        self.assert_semantic_rejection(draft, packet)

    def share_direction_candidate(self, page, old_text, new_text):
        """Keep the real typed facts and a gate-valid three-layer baseline."""
        packet = self.packet(page)
        draft = business_fact_draft(page, packet, MONTH)
        validate_business_slide(draft, packet)
        matching = [claim for claim in draft["body_claims"] if old_text in claim["claim"]]
        self.assertEqual(len(matching), 1, "the named real share assertion must remain in the fixture")
        matching[0]["claim"] = matching[0]["claim"].replace(old_text, new_text)
        return draft, packet

    def test_origin_negative_pp_cannot_be_reported_as_bare_higher_value(self):
        draft, packet = self.share_direction_candidate(12,
            "自主份额较上月回落0.6个百分点至69.7%", "自主份额69.7%，较上月高0.6")
        own = _record(packet, "自主", "P2-6.1")
        self.assertEqual(own["share_change_pp"], -0.6)
        self.assertEqual(own["share_comparison_scope"], "previous_month")
        self.assert_semantic_rejection(draft, packet)

    def test_origin_negative_pp_cannot_be_reported_as_higher_percentage_points(self):
        draft, packet = self.share_direction_candidate(12,
            "自主份额较上月回落0.6个百分点至69.7%", "自主份额较上月高0.6个百分点至69.7%")
        self.assert_semantic_rejection(draft, packet)

    def test_nev_positive_pp_cannot_be_reported_as_bare_lower_value(self):
        draft, packet = self.share_direction_candidate(17, "较上月提高0.8个百分点", "较上月低0.8")
        self.assertEqual(_record(packet, "新能源", "P2-11.1")["share_change_pp"], 0.8)
        self.assert_semantic_rejection(draft, packet)

    def test_region_negative_pp_cannot_be_reported_as_bare_higher_value(self):
        draft, packet = self.share_direction_candidate(14,
            "中部份额较去年同期回落1.2个百分点至20.2%", "中部份额20.2%，较去年同期高1.2")
        self.assertEqual(_record(packet, "中部", "P2-8.2")["share_change_pp"], -1.2)
        self.assert_semantic_rejection(draft, packet)

    def test_city_negative_pp_cannot_be_reported_as_bare_higher_value(self):
        draft, packet = self.share_direction_candidate(15,
            "一线城市份额较上月回落0.5个百分点至10.4%", "一线城市份额10.4%，较上月高0.5")
        self.assertEqual(_record(packet, "一线城市", "P2-9.1")["share_change_pp"], -0.5)
        self.assert_semantic_rejection(draft, packet)

    def test_negative_share_expansion_cannot_use_the_decline_expansion_sign_rule(self):
        draft, packet = self.share_direction_candidate(12,
            "自主份额较上月回落0.6个百分点至69.7%", "自主份额69.7%，较上月扩大0.6个百分点")
        self.assert_semantic_rejection(draft, packet)

    def test_positive_share_narrowing_cannot_use_the_decline_narrowing_sign_rule(self):
        draft, packet = self.share_direction_candidate(17,
            "较上月提高0.8个百分点", "较上月收窄0.8个百分点")
        self.assert_semantic_rejection(draft, packet)

    def test_growth_verb_with_negative_pp_magnitude_is_not_a_valid_direction(self):
        draft, packet = self.share_direction_candidate(12,
            "自主份额较上月回落0.6个百分点至69.7%", "自主份额69.7%，较上月提高-0.6个百分点")
        self.assert_semantic_rejection(draft, packet)

    def test_qualitative_yoy_growth_cannot_hide_negative_yoy_by_omitting_number(self):
        draft, packet = self.fixture(17)
        draft["headline"] = "新能源同比增长而传统车同比下降，能源规模方向分化"
        self.assert_semantic_rejection(draft, packet)

    def test_inventory_synchronous_decline_is_rejected_in_headline_and_body(self):
        original, packet = self.fixture(5)
        for location in ("headline", "body"):
            with self.subTest(location=location):
                draft = deepcopy(original)
                if location == "headline":
                    draft["headline"] = "新能源与传统车库存同步下降，行业去化方向一致"
                else:
                    draft["body_claims"][1]["claim"] = "新能源库存202.5万辆、传统车库存209.5万辆，两种能源库存同步下降，去化方向一致，库存与零售仍需分别观察。"
                self.assert_semantic_rejection(draft, packet)

    def test_origin_mom_cannot_be_quoted_as_yoy(self):
        draft, packet = self.fixture(12)
        draft["body_claims"][1]["claim"] = draft["body_claims"][1]["claim"].replace("韩系环比下降18.4%", "韩系同比下降18.4%")
        self.assert_semantic_rejection(draft, packet)

    def test_current_share_cannot_borrow_year_to_date_share(self):
        draft, packet = self.fixture(12)
        draft["body_claims"][0]["claim"] = "8月自主单月份额64.7%，日系同比下降34.8%，两者降幅不同，份额优势不能代替销量增长，口径不能相互混用。"
        draft["body_claims"][0]["fact_ids"].append(_record(packet, "自主", "P2-6.2", "year_to_date")["fact_id"])
        self.assert_semantic_rejection(draft, packet)

    def test_explicit_single_month_cannot_fall_back_to_a_ytd_only_reference(self):
        draft, packet = self.fixture(17)
        draft["body_claims"][2]["claim"] = draft["body_claims"][2]["claim"].replace("新能源累计零售646.4", "新能源单月零售646.4")
        self.assert_semantic_rejection(draft, packet)

    def test_ytd_cannot_be_called_full_year(self):
        draft, packet = self.fixture(17)
        draft["body_claims"][2]["claim"] = draft["body_claims"][2]["claim"].replace("累计零售", "全年零售")
        self.assert_semantic_rejection(draft, packet)

    def test_region_year_headers_do_not_turn_same_month_totals_into_ytd(self):
        packet = self.packet(14)
        draft = business_fact_draft(14, packet, MONTH)
        validate_business_slide(draft, packet)
        self.assertTrue(all(row["scope"] == "single_month" for row in packet["business_facts"]
                            if row["source_card_code"] == "P2-8.2"))
        draft["body_claims"][0]["claim"] = draft["body_claims"][0]["claim"].replace("8月", "1—8月累计", 1)
        self.assert_semantic_rejection(draft, packet)

    def test_sales_quantity_cannot_be_relabelled_inventory(self):
        draft, packet = self.fixture(17)
        draft["body_claims"][0]["claim"] = draft["body_claims"][0]["claim"].replace("新能源单月零售", "新能源单月库存")
        self.assert_semantic_rejection(draft, packet)

    def test_positive_group_net_gain_cannot_be_written_as_net_decline(self):
        draft, packet = self.fixture(8)
        draft["body_claims"][1]["claim"] = draft["body_claims"][1]["claim"].replace("合计环比净增", "合计环比净减")
        self.assert_semantic_rejection(draft, packet)

    def test_page_18_cannot_swap_nev_and_passenger_market_denominators(self):
        draft, packet = self.fixture(18)
        draft["body_claims"][1]["claim"] = draft["body_claims"][1]["claim"].replace("70.0%", "PLACEHOLDER").replace("44.2%", "70.0%").replace("PLACEHOLDER", "44.2%")
        self.assert_semantic_rejection(draft, packet)

    def test_enterprise_observed_subset_cannot_be_called_unique_market_leader(self):
        draft, packet = self.fixture(16)
        draft["headline"] = "奇瑞汽车是全市场唯一环比领涨企业"
        self.assertFalse(next(value for value in packet["coverage"]["groups"] if value["card_code"] == "P2-10.1")["complete"])
        self.assert_semantic_rejection(draft, packet)

    def test_typed_fact_reference_requires_exact_entity_scope_and_period(self):
        draft, packet = self.fixture(17)
        draft["body_claims"][0]["fact_ids"][0] = "P2-11.1"
        self.assert_semantic_rejection(draft, packet)

    def overview_fixture(self):
        packets, approved = [], []
        for page in BUSINESS_PAGES:
            packet = self.packet(page)
            draft = business_fact_draft(page, packet, MONTH)
            validate_business_slide(draft, packet)
            packets.append(packet)
            approved.append(draft)
        packet = overview_business_packet(packets, approved, MONTH)
        self.assertIsNotNone(packet)
        draft = deepcopy(packet["fact_grounded_draft"])
        validate_business_slide(draft, packet)
        return draft, packet

    def test_overview_nev_cannot_borrow_share_through_passenger_retail_paraphrase(self):
        draft, packet = self.overview_fixture()
        draft["body_claims"][1]["claim"] = draft["body_claims"][1]["claim"].replace(
            "新能源占整体市场63.2%", "新能源占全国乘用车零售36.8%")
        self.assert_semantic_rejection(draft, packet)

    def test_overview_nev_cannot_change_market_share_denominator_to_nev_itself(self):
        draft, packet = self.overview_fixture()
        draft["body_claims"][1]["claim"] = draft["body_claims"][1]["claim"].replace(
            "新能源占整体市场63.2%", "新能源占全部新能源销量63.2%")
        self.assert_semantic_rejection(draft, packet)

    def future_packet(self, page):
        packet = self.packet(page)
        future = "2026-09"
        def shift(period):
            year, month = map(int, period.split("-"))
            return f"{year + (month == 12)}-{1 if month == 12 else month + 1:02d}"
        def shift_id(value):
            return re.sub(r"\d{4}-\d{2}$", lambda match: shift(match[0]), value)
        for row in packet["business_facts"]:
            row["period"] = shift(row["period"])
            row["fact_id"] = shift_id(row["fact_id"])
            row["source_fact_ids"] = [shift_id(value) for value in row.get("source_fact_ids", [])]
            row["denominator_source_fact_ids"] = [shift_id(value) for value in row.get("denominator_source_fact_ids", [])]
            for key in ("comparison_period", "previous_period", "period_end"):
                if key in row:
                    row[key] = shift(row[key])
            if row["period"] != future or row["metric"] not in ("sales", "inventory"):
                continue
            # A positive local counterfactual with calculable operands, not a
            # negative August assertion copied into a new date.
            value = row["value"]
            baseline = max(1, int(value / 1.12))
            previous = max(1, int(value / 1.06))
            row["comparison_value"] = baseline
            row["delta_yoy"] = value - baseline
            row["yoy_pct"] = round((value / baseline - 1) * 100, 1)
            row["operands"].update(current_value=value, comparison_value=baseline)
            if row["scope"] != "year_to_date":
                row["previous_value"] = previous
                row["delta_mom"] = value - previous
                row["mom_pct"] = round((value / previous - 1) * 100, 1)
                row["operands"]["previous_value"] = previous
            if row.get("denominator_value"):
                denominator = row["denominator_value"]
                comparison_total = max(1, int(denominator / 1.12))
                row["operands"]["comparison_total_value"] = comparison_total
                row["comparison_share_pct"] = round(baseline / comparison_total * 100, 1)
                if row["share_comparison_scope"] == "previous_month":
                    previous_total = max(1, int(denominator / 1.06))
                    row["operands"]["previous_total_value"] = previous_total
                    row["previous_share_pct"] = round(previous / previous_total * 100, 1)
                    row["share_change_pp"] = round((value / denominator - previous / previous_total) * 100, 1)
                else:
                    row["share_change_pp"] = round((value / denominator - baseline / comparison_total) * 100, 1)
            row.pop("source_method", None)
            row.pop("yoy_source_method", None)
            row.pop("observed_yoy_pct", None)
            row.pop("percent_operands", None)
            row["method"] = "counterfactual test quantities; rate=(current/baseline-1)*100"
        packet["coverage"]["period"] = future
        for coverage in packet["coverage"]["groups"]:
            coverage["period"] = future
            coverage["observed_periods"] = [shift(value) for value in coverage["observed_periods"]]
        return packet, future

    def assert_positive_future_draft(self, page):
        packet, future = self.future_packet(page)
        draft = business_fact_draft(page, packet, future)
        text = "\n".join([draft["headline"], *(claim["claim"] for claim in draft["body_claims"])])
        self.assertIn("9月", text)
        self.assertNotIn("8月", text)
        self.assertNotRegex(text, r"同比下降|环比下降|净减|承压|收缩|普降|抗跌|同比压力|降幅")
        validate_business_slide(draft, packet)
        refs = {value for claim in draft["body_claims"] for value in claim["fact_ids"]}
        self.assertTrue(all(fact_id.endswith(future) for fact_id in refs))

    def test_future_region_without_ytd_does_not_invent_inventory_metric(self):
        packet, future = self.future_packet(14)
        self.assertFalse(any(row["metric"] == "inventory" for row in packet["business_facts"]))
        draft = business_fact_draft(14, packet, future)
        text = "\n".join(claim["claim"] for claim in draft["body_claims"])
        self.assertNotIn("库存", text)

    def test_future_equal_rates_do_not_claim_unequal_recovery(self):
        packet, future = self.future_packet(17)
        current = [row for row in packet["business_facts"]
                   if row["period"] == future and row["scope"] == "single_month"]
        self.assertEqual({row["mom_pct"] for row in current}, {6.0})
        draft = business_fact_draft(17, packet, future)
        text = "\n".join(claim["claim"] for claim in draft["body_claims"])
        self.assertNotRegex(text, r"恢复幅度不同|回升幅度不同|一快一慢")

    def test_future_positive_page_4(self): self.assert_positive_future_draft(4)
    def test_future_positive_page_5(self): self.assert_positive_future_draft(5)
    def test_future_positive_page_7(self): self.assert_positive_future_draft(7)
    def test_future_positive_page_8(self): self.assert_positive_future_draft(8)
    def test_future_positive_page_12(self): self.assert_positive_future_draft(12)
    def test_future_positive_page_13(self): self.assert_positive_future_draft(13)
    def test_future_positive_page_14(self): self.assert_positive_future_draft(14)
    def test_future_positive_page_15(self): self.assert_positive_future_draft(15)
    def test_future_positive_page_16(self): self.assert_positive_future_draft(16)
    def test_future_positive_page_17(self): self.assert_positive_future_draft(17)
    def test_future_positive_page_18(self): self.assert_positive_future_draft(18)
    def test_future_positive_page_19(self): self.assert_positive_future_draft(19)


if __name__ == "__main__":
    unittest.main()
