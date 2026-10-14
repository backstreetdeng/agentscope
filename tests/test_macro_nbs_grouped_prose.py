import copy
from hashlib import sha256
import importlib.util
import json
from pathlib import Path
import unittest

PROJECT = Path(__file__).resolve().parents[1]
SCRIPTS = PROJECT / "skills/macro-monthly-report/scripts"
spec = importlib.util.spec_from_file_location("grouped_prose_tests", SCRIPTS / "macro_nbs_grouped_prose.py")
reader = importlib.util.module_from_spec(spec)
spec.loader.exec_module(reader)


def requests():
    result = []
    for name in ("PMI", "PMI:大型企业", "PMI:中型企业", "PMI:小型企业"):
        aliases = ["制造业采购经理指数", "制造业PMI", "PMI"] if name == "PMI" else [name.split(":")[1]]
        result.append({"id": "s11-shape12::" + name, "chart_id": "s11-shape12", "series_name": name,
                       "definition": "制造业PMI企业规模：" + name, "definition_aliases": aliases,
                       "unit": "指数", "frequency": "monthly", "source_domains": ["stats.gov.cn"]})
    for index, (label, _) in reader.PMI_COMPONENTS.items():
        result.append({"id": "s11-shape15::category" + str(index), "chart_id": "s11-shape15", "series_name": "snapshot",
                       "category_index": index, "definition": "PMI分项指数：" + label,
                       "definition_aliases": [label, label + "指数"], "unit": "指数", "frequency": "monthly",
                       "source_domains": ["stats.gov.cn"]})
    for cid, metric in (("s18-shape17", "环比"), ("s18-shape21", "同比")):
        for tier in ("一线城市", "二线城市", "三线城市"):
            result.append({"id": cid + "::" + tier, "chart_id": cid, "series_name": tier,
                           "definition": "70城新房" + metric + "：" + tier, "definition_aliases": [tier],
                           "unit": "%", "frequency": "monthly", "source_domains": ["stats.gov.cn"]})
    return result


def page(text, published="2026-09-30", path="xxgk/sjfb/zxfb2020"):
    return {"url": "https://www.stats.gov.cn/" + path + "/" + published[:7].replace("-", "") + "/t" + published.replace("-", "") + "_1965000.html",
            "text": text, "published_at": published, "receipt_id": "synthetic-reviewed-original",
            "text_sha256": sha256(text.encode()).hexdigest(), "truncated": False}


def pmi(group="大、中、小型企业PMI分别为50.6%、49.7%和48.9%", year=2026, month=9):
    text = (f"国家统计局信息公开\n成文日期\n{year}年{month:02d}月30日\n国家统计局服务业调查中心\n中国物流与采购联合会\n"
            f"一、中国制造业采购经理指数运行情况\n{month}月份，制造业采购经理指数（PMI）为50.1%，比上月上升0.3个百分点。\n"
            f"从企业规模看，{group}，比上月变化0.3个百分点。\n"
            "生产指数为51.7%，比上月上升1.3个百分点。\n新订单指数为50.5%，比上月下降0.1个百分点。\n"
            "原材料库存指数为48.2%，比上月上升0.1个百分点。\n从业人员指数为48.4%，比上月下降0.3个百分点。\n"
            "供应商配送时间指数为50.1%，与上月持平。\n表1 中国制造业PMI及构成指数（经季节调整）\n"
            "二、中国非制造业采购经理指数运行情况\n生产指数为88.8%，供应商配送时间指数为99.9%。")
    return page(text, f"{year}-{month:02d}-30")


def housing():
    text = ("国家统计局信息公开\n成文日期\n2026年09月15日\n"
            "——国家统计局城市司高级统计师解读2026年8月份商品住宅销售价格变动情况统计数据\n"
            "2026年8月份，70个大中城市中，一线城市价格环比上涨。\n"
            "8月份，一线城市新建商品住宅销售价格环比由上月上涨0.9%转为持平。"
            "其中，上海上涨9.9%。二线城市新建商品住宅销售价格环比下降0.1%。三线城市新建商品住宅销售价格环比下降0.2%。\n"
            "8月份，一线城市二手住宅销售价格环比上涨0.8%。二、三线城市二手住宅销售价格环比分别下降0.4%和0.7%。\n"
            "8月份，一线城市新建商品住宅销售价格同比下降0.9%，降幅比上月收窄0.2个百分点。"
            "其中，北京下降2.3%。二、三线城市新建商品住宅销售价格同比分别下降2.7%和4.1%。\n"
            "8月份，一线城市二手住宅销售价格同比下降2.7%。\n"
            "70个大中城市房地产价格统计一二三线城市划分：一线城市指北京等4个城市；二线城市指天津等31个城市；三线城市指唐山等35个城市。")
    return page(text, "2026-09-15", "xxgk/jd/sjjd2020")


def changed(original, old, new):
    return dict(original, text=original["text"].replace(old, new),
                text_sha256=sha256(original["text"].replace(old, new).encode()).hexdigest())


class GroupedProseTests(unittest.TestCase):
    def test_three_pmi_enterprises_number_order_and_index_scale(self):
        original = pmi(); candidates = reader.reviewed_grouped_prose_candidates(original, requests())
        self.assertEqual(len(candidates), 9)
        self.assertEqual([c["value"] for c in candidates[:4]], [50.1, 50.6, 49.7, 48.9])
        for index, candidate in enumerate(candidates[1:4]):
            proof = candidate["nbs_grouped_prose_proof"]
            self.assertEqual(proof["member_index"], index)
            self.assertEqual(proof["group_order"], ["大型企业", "中型企业", "小型企业"])
            self.assertEqual(candidate["unit"], "指数")
            self.assertEqual(original["text"][slice(*proof["value_offsets"])], candidate["value_text"])

    def test_individual_and_mixed_enterprise_group_shapes(self):
        variants = ["大型企业PMI为50.6%；中、小型企业PMI分别为49.7%和48.9%",
                    "大型企业PMI为50.6%；中型企业PMI为49.7%；小型企业PMI为48.9%"]
        for variant in variants:
            original = pmi(variant)
            candidates = reader.reviewed_grouped_prose_candidates(original, requests())
            self.assertEqual([c["value"] for c in candidates[1:4]], [50.6, 49.7, 48.9])

    def test_only_manufacturing_current_prose_not_nonmanufacturing_or_change(self):
        original = pmi()
        candidates = reader.reviewed_grouped_prose_candidates(original, requests())
        self.assertEqual(candidates[4]["value"], 51.7)
        self.assertEqual(candidates[-1]["value"], 50.1)
        self.assertNotIn(99.9, [c["value"] for c in candidates])
        self.assertNotIn(1.3, [c["value"] for c in candidates])

    def test_non_current_prediction_and_non_unique_groups_rejected(self):
        original = pmi()
        altered = changed(original, "生产指数为", "预计生产指数为")
        self.assertNotIn("s11-shape15::category0", [c["request_id"] for c in reader.reviewed_grouped_prose_candidates(altered, requests())])
        altered = changed(original, "从企业规模看，", "大型企业PMI为40.0%。从企业规模看，")
        self.assertNotIn("s11-shape12::PMI:大型企业", [c["request_id"] for c in reader.reviewed_grouped_prose_candidates(altered, requests())])

    def test_period_not_navigation_or_url_and_year_not_fixed(self):
        original = pmi(year=2027)
        candidates = reader.reviewed_grouped_prose_candidates(original, requests(), "2027-10-03", "2027-09")
        self.assertEqual(len(candidates), 9)
        self.assertEqual(candidates[0]["period"], "2027-09")
        self.assertEqual(reader.reviewed_grouped_prose_candidates(changed(original, "9月份，", "8月份，"), requests()), [])
        self.assertEqual(reader.reviewed_grouped_prose_candidates(changed(original, "成文日期", "导航日期"), requests()), [])

    def test_duplicate_identical_mobile_body_allowed_but_conflicts_rejected(self):
        original = pmi(); body = original["text"].split("一、中国制造业")[1].split("二、中国非制造业")[0]
        extra = "一、中国制造业" + body
        duplicate = changed(original, "二、中国非制造业", extra + "二、中国非制造业")
        self.assertEqual(len(reader.reviewed_grouped_prose_candidates(duplicate, requests())), 9)
        conflicting = changed(original, "二、中国非制造业", extra.replace("51.7%", "51.8%") + "二、中国非制造业")
        self.assertEqual(reader.reviewed_grouped_prose_candidates(conflicting, requests()), [])

    def test_new_homes_order_signed_decline_and_current_zero(self):
        original = housing(); candidates = reader.reviewed_grouped_prose_candidates(original, requests())
        self.assertEqual(len(candidates), 6)
        self.assertEqual([c["value"] for c in candidates], [0.0, -0.1, -0.2, -0.9, -2.7, -4.1])
        self.assertEqual(candidates[0]["value_text"], "0")
        for candidate in candidates:
            request = next(q for q in requests() if q["id"] == candidate["request_id"])
            result = reader.verify_grouped_prose_candidate(candidate, request, original)
            self.assertEqual(result["explicit_unchanged_zero_verified"], candidate["value"] == 0)
            self.assertTrue(result["reviewed_period_and_definition"])
            self.assertNotIn("二手", candidate["quote"])
        self.assertEqual(candidates[-1]["nbs_grouped_prose_proof"]["member_index"], 1)

    def test_housing_title_summary_scope_and_new_vs_second_hand_guards(self):
        original = housing()
        for before, after in [("解读2026年8月份", "解读2025年8月份"), ("2026年8月份，70个", "2026年7月份，70个"),
                              ("新建商品住宅", "二手住宅"), ("70个大中城市房地产价格统计", "35个城市价格统计"),
                              ("一线城市新建商品住宅销售价格环比", "一线城市新建商品住宅销售价格累计环比")]:
            altered = changed(original, before, after)
            candidates = reader.reviewed_grouped_prose_candidates(altered, requests())
            if "累计" in after:
                self.assertFalse(any(c["request_id"].startswith("s18-shape17") for c in candidates))
            else:
                self.assertEqual(candidates, [])

    def test_preserves_transition_to_positive_and_negative_not_previous_value(self):
        original = housing()
        for replacement, value in [("上涨0.2%", 0.2), ("下降0.3%", -0.3)]:
            altered = changed(original, "转为持平", "转为" + replacement)
            candidate = reader.reviewed_grouped_prose_candidates(altered, requests())[0]
            self.assertEqual(candidate["value"], value)
            self.assertNotEqual(candidate["value"], 0.9)

    def test_unknown_request_category_alias_unit_scope_frequency_rejected(self):
        for original in (pmi(), housing()):
            q = next(q for q in requests() if reader.reviewed_grouped_prose_candidates(original, [q]))
            for modification in [{"definition_aliases": ["二手住宅"]}, {"definition": "累计值"},
                                 {"frequency": "annual"}, {"unit": "百分点"}, {"source_domains": ["wind.com"]},
                                 {"id": "unknown"}]:
                self.assertEqual(reader.reviewed_grouped_prose_candidates(original, [{**q, **modification}]), [])
        q = next(q for q in requests() if q["id"] == "s11-shape15::category0")
        self.assertEqual(reader.reviewed_grouped_prose_candidates(pmi(), [{**q, "category_index": True}]), [])

    def test_original_hash_publisher_publication_date_cutoff_and_target_guards(self):
        original = housing()
        for modification in [{"text_sha256": "fake"}, {"truncated": True}, {"url": "https://evil.test/article.html"},
                             {"published_at": "2026-09-16"}, {"receipt_id": ""}]:
            self.assertEqual(reader.reviewed_grouped_prose_candidates({**original, **modification}, requests()), [])
        self.assertEqual(reader.reviewed_grouped_prose_candidates(original, requests(), "2026-09-14"), [])
        self.assertEqual(reader.reviewed_grouped_prose_candidates(original, requests(), report_month="2026-07"), [])

    def test_arbitrary_candidates_cannot_forge_order_offsets_sign_period_or_zero(self):
        original = housing(); candidates = reader.reviewed_grouped_prose_candidates(original, requests())
        for candidate in (candidates[0], candidates[-1]):
            request = next(q for q in requests() if q["id"] == candidate["request_id"])
            for modification in [{"value": True}, {"value": 0.9}, {"value_text": "0.9"}, {"unit": "指数"},
                                 {"period": "2026-09"}, {"definition_quote": "二手住宅"}, {"observation_kind": "forecast"},
                                 {"published_at": "2026-09-16"}]:
                with self.assertRaises(ValueError):
                    reader.verify_grouped_prose_candidate({**candidate, **modification}, request, original)
            for modification in [{"member_index": True}, {"group_order": ["三线城市", "二线城市"]},
                                 {"direction": "上涨"}, {"value_offsets": [1, 9]}, {"profile": "any_prose"}]:
                forged = copy.deepcopy(candidate); forged["nbs_grouped_prose_proof"].update(modification)
                with self.assertRaises(ValueError):
                    reader.verify_grouped_prose_candidate(forged, request, original)

    def test_real_fifteen_requests_three_months_forty_five_literal_replays(self):
        cache = PROJECT / ".work/macro-public-run/codex-run-v3/working/macro-sources/pages"
        contract = PROJECT / "runtime/skill-runs/macro-20261004-005541-c8ad8701/working/template-contract.json"
        if not cache.exists() or not contract.exists():
            self.skipTest("Retained official receipts and actual template contract are required for local replay")
        qs = json.loads(contract.read_text(encoding="utf-8"))["source_requests"]
        files = ["fac43ff52cb70db246b2052bfd56881bdb930b7a1369da6ceff7fd299e254ae7",
                 "9675e5d6a8698cd2df2f97946bd61ccb315fbb6b67f01fc46b21c584d593ad4d",
                 "0a74d2361229b9356f96a08f14597346d41d0e2441211894391b05d94865c9fb",
                 "390ff139f5e3497b4381b7aa1f10c0bc83ceca9a808d8ea7bb1217675f977b78",
                 "adbe1dd1703b716354c73bae966200ff24345a04b6e7f348b4961932c617dd43",
                 "5053b1a86c3f1c53330dab0e1832192312a6c6342a8dd497ef65d6e62a284678"]
        verified, zeros = set(), []
        for index, filename in enumerate(files):
            original = json.loads((cache / (filename + ".json")).read_text(encoding="utf-8"))
            candidates = reader.reviewed_grouped_prose_candidates(original, qs, "2026-10-03", "2026-09")
            self.assertEqual(len(candidates), 9 if index < 3 else 6)
            for candidate in candidates:
                request = next(q for q in qs if q["id"] == candidate["request_id"])
                result = reader.verify_grouped_prose_candidate(candidate, request, original, "2026-10-03", "2026-09")
                self.assertTrue(result["reviewed_period_and_definition"])
                verified.add((candidate["request_id"], candidate["period"]))
                if result["explicit_unchanged_zero_verified"]:
                    zeros.append((candidate["request_id"], candidate["period"]))
        self.assertEqual(len(verified), 45)
        self.assertEqual(len({rid for rid, _ in verified}), 15)
        self.assertEqual(set(zeros), {("s18-shape17::二线城市", "2026-06"), ("s18-shape17::一线城市", "2026-07")})


if __name__ == "__main__":
    unittest.main()
