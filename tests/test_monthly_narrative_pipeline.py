from __future__ import annotations

import json
import tempfile
import unittest
from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from pathlib import Path

from tools.monthly_report_browser import _card_has_current_period
from utils.monthly_report_narrative import (
    _compact_card_facts,
    _evidence_payload,
    _extract_json,
    _format_business_text,
    _deterministic_overview,
    _model_payload,
    _ppt_narrative_text,
    _save_reply_diagnostic,
    _structured_retry_config,
    _validate_batch_facts,
    _validate_overview_numbers,
    _validate_segment_support,
    _display_width,
    _wrap_business_text,
    generate_monthly_narratives,
)
from utils.monthly_segment_facts import segment_page_facts


class MonthlyNarrativePipelineTest(unittest.TestCase):
    def test_card_freshness_requires_current_period(self) -> None:
        old = "P2-1.1：车型类别\n日期组合 (月)\n2025-08\n100\n"
        current = old + "2026-08\n80\n"
        self.assertFalse(_card_has_current_period("P2-1.1", old, "2026-08"))
        self.assertTrue(_card_has_current_period("P2-1.1", current, "2026-08"))

    def test_cumulative_card_accepts_current_year(self) -> None:
        text = "P2-1.2：车型类别-累计\n年\n2025\n100\n2026\n80\n"
        self.assertTrue(_card_has_current_period("P2-1.2", text, "2026-08"))

    def test_model_payload_excludes_raw_trace_metadata(self) -> None:
        raw = (
            "P1.1-1：整体销量\n日期组合 (月)\n销量\n同比\n"
            "2026-07\n100\n-10.0%\n2026-08\n105\n-8.0%\n"
        )
        card = _compact_card_facts("P1.1-1", raw, "2026-08")
        payload = _model_payload([{
            "slide": 4,
            "required_prefix": "1.2 零售量",
            "card_codes": ["P1.1-1"],
            "cards": [card],
            "expert_style_profile": {"rules": ["对象与方向明确"]},
        }])
        model_card = payload[0]["cards"][0]
        self.assertNotIn("raw_sha256", model_card)
        self.assertNotIn("raw_char_count", model_card)
        self.assertIn("2026-08", model_card["facts"])

    def test_evidence_tools_never_receive_internal_measurements(self) -> None:
        payload = [{
            "slide": 16,
            "required_prefix": "2.7 企业竞争",
            "cards": [{
                "period": "2026-08",
                "facts": ["比亚迪汽车", "231511", "14.9%", "吉利汽车"],
                "candidate_signals": [{"type": "share_or_rank_shift", "value": 14.9}],
            }],
        }]
        query_plan = _evidence_payload(payload)[0]
        self.assertEqual(query_plan["public_entities"], ["比亚迪汽车", "吉利汽车"])
        self.assertNotIn("231511", str(query_plan))
        self.assertNotIn("14.9", str(query_plan))

    def test_extract_json_from_fenced_reply_and_repairs_trailing_comma(self) -> None:
        value = _extract_json('说明如下\n```json\n{"slides": [],}\n```')
        self.assertEqual(value, {"slides": []})

    def test_extract_json_rejects_unfinished_thinking_only_reply(self) -> None:
        with self.assertRaisesRegex(ValueError, "思考阶段"):
            _extract_json("<think>仍在推理，没有最终JSON")

    def test_extract_json_rejects_none_reply_as_missing_final_content(self) -> None:
        with self.assertRaisesRegex(ValueError, "思考阶段"):
            _extract_json(None)

    def test_minimax_structured_retry_disables_thinking_without_mutating_source(self) -> None:
        config = {
            "active_provider": "minimax",
            "providers": {
                "minimax": {
                    "model": "MiniMax-M3",
                    "temperature": 0.3,
                    "extra_body": {"reasoning_split": True},
                },
            },
        }
        retry = _structured_retry_config(config)
        self.assertEqual(retry["providers"]["minimax"]["temperature"], 0.1)
        self.assertEqual(
            retry["providers"]["minimax"]["extra_body"]["thinking"],
            {"type": "disabled"},
        )
        self.assertNotIn("thinking", config["providers"]["minimax"]["extra_body"])

    def test_reply_diagnostic_keeps_final_text_but_not_thinking_content(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            run_dir = Path(directory)
            _save_reply_diagnostic(
                run_dir,
                "B2",
                1,
                '<think>内部推理</think>\n{"slides": []}',
                None,
            )
            saved = (run_dir / "model-final-B2-attempt-1.txt").read_text(encoding="utf-8")
            meta = json.loads((run_dir / "model-reply-B2-attempt-1.json").read_text(encoding="utf-8"))
            self.assertEqual(saved, '{"slides": []}')
            self.assertNotIn("内部推理", saved)
            self.assertTrue(meta["contained_thinking_tag"])

    def test_evidence_reply_diagnostic_uses_separate_files(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            run_dir = Path(directory)
            _save_reply_diagnostic(
                run_dir,
                "B2",
                1,
                '{"evidence": []}',
                ValueError("invalid evidence"),
                stage="evidence",
            )
            saved = (run_dir / "evidence-final-B2-attempt-1.txt").read_text(encoding="utf-8")
            meta = json.loads((run_dir / "evidence-reply-B2-attempt-1.json").read_text(encoding="utf-8"))
            self.assertEqual(saved, '{"evidence": []}')
            self.assertEqual(meta["error"], "invalid evidence")
            self.assertFalse((run_dir / "model-final-B2-attempt-1.txt").exists())

    def test_fact_validation_accepts_thousands_separator_and_wan_conversion(self) -> None:
        payload = [{
            "slide": 9,
            "required_prefix": "2.3 轿车级别",
            "card_codes": ["P2-3.1"],
            "cards": [{
                "fact_id": "P2-3.1",
                "period": "2026-08",
                "facts": ["2026-08", "39671", "21800"],
                "candidate_signals": [],
            }],
        }]
        batch = {"slides": [{
            "slide": 9,
            "headline": "2.3 轿车级别：销量39,671辆",
            "anomaly": {"type": "ordinary_change", "fact_ids": ["P2-3.1"]},
            "body_claims": [{"claim": "累计约2.18万辆", "fact_ids": ["P2-3.1"]}],
        }]}
        _validate_batch_facts(batch, payload)

    def test_business_text_uses_chinese_month_and_vehicle_units(self) -> None:
        text = _format_business_text(
            "2026-08智界V9销量8,294辆，A0级71,655辆，C+级142,185辆",
            "2026-08",
        )
        self.assertEqual(text, "8月智界V9销量8294辆，A0级7.2万辆，C+级14.2万辆")

    def test_ppt_narrative_keeps_multiple_evidence_layers_in_one_paragraph(self) -> None:
        item = {
            "headline": "2.3 SUV级别：2026-08 A0、B级环比转正，C+级转负",
            "body_claims": [
                {"claim": "2026-08 A0级71,655辆，环比增长17.6%，B级环比增长3.7%。"},
                {"claim": "特斯拉Model Y销量24,419辆，同比下降37.6%，其他车型信息不再逐项展开。"},
            ],
        }
        headline, body = _ppt_narrative_text(item, "2026-08")
        self.assertNotIn("2026-08", headline + body)
        self.assertIn("7.2万辆", body)
        self.assertIn("Model Y", body)
        self.assertIn("；", body)
        self.assertNotIn(",", body)

    def test_fact_validation_rejects_unmeasured_primary_drag_claim(self) -> None:
        payload = [{
            "slide": 10,
            "required_prefix": "2.3 SUV级别",
            "card_codes": ["P2-4.1"],
            "cards": [{
                "fact_id": "P2-4.1",
                "period": "2026-08",
                "facts": ["2026-08", "24419"],
                "candidate_signals": [],
            }],
        }]
        batch = {"slides": [{
            "slide": 10,
            "headline": "2.3 SUV级别：Model Y为主要拖累",
            "anomaly": {"type": "ordinary_change", "fact_ids": ["P2-4.1"]},
            "body_claims": [],
        }]}
        with self.assertRaisesRegex(ValueError, "贡献测算"):
            _validate_batch_facts(batch, payload)

    def test_period_labelled_model_rows_do_not_shift_missing_cells(self) -> None:
        text = ("P2-4.3A：车型\n---视图分段---\n数量\n车型\n"
                "2025-10\n2025-11\n2026-10\n2026-11\n"
                "新车型X\n9000\n9500\n老车型Y\n10000\n20000\n25000\n30000\n-1.0%\n50.0%\n")
        payload = segment_page_facts(10, {"P2-4.3A": {"text": text}}, "2026-11")
        models = payload["model_facts"]
        self.assertEqual([row["model"] for row in models], ["老车型Y"])
        self.assertEqual(models[0]["sales"], 30000)
        self.assertEqual(models[0]["yoy_pct"], 50.0)
        self.assertEqual(models[0]["mom_pct"], 20.0)

    def test_month_and_cumulative_level_shares_are_separate(self) -> None:
        cards = {
            "P2-3.1": {"text": "数量\n数量\n日期组合 (月)\nA\nB\n2026-08\n100\n300\n"},
            "P2-3.2": {"text": "数量\n数量\n年\nA\nB\n2026\n900\n100\n"},
        }
        rows = segment_page_facts(9, cards, "2026-08")["level_facts"]
        self.assertEqual([(row["scope"], row["level"], row["share_pct"]) for row in rows],
                         [("single_month", "A", 25.0), ("single_month", "B", 75.0),
                          ("year_to_date", "A", 90.0), ("year_to_date", "B", 10.0)])

    def _supported_segment(self):
        models = [
            {"fact_id": "P2-4.3A:车型甲:2026-08", "model": "车型甲", "period": "2026-08",
             "sales": 24419, "yoy_pct": -37.6, "mom_pct": 14.8},
            {"fact_id": "P2-4.3A:车型乙:2026-08", "model": "车型乙", "period": "2026-08",
             "sales": 21984, "yoy_pct": 14.6, "mom_pct": 10.6},
        ]
        payload = {"slide": 10, "model_facts": models,
                   "coverage_requirement": {"minimum_models": 2}}
        slide = {"slide": 10, "headline": "2.3 SUV级别：级别结构分化",
                 "body_claims": [
                     {"role": "core", "claim": "8月SUV级别表现分化，A0级市场环比回升，B级市场同比仍然承压，部分级别的环比改善没有改变同比下降的总体方向。"},
                     {"role": "structure", "claim": "累计结构上，两端级别的市场份额增加，主流级别的占比收缩，单月回升与累计结构调整并存，应区分观察口径。"},
                     {"role": "models", "claim": "车型甲2.4万辆同比下降37.6%，车型乙2.2万辆同比增长14.6%，代表车型走势形成对照。",
                      "fact_ids": [row["fact_id"] for row in models]},
                 ]}
        return slide, payload

    def test_model_metrics_survive_render_and_are_entity_paired(self) -> None:
        slide, payload = self._supported_segment()
        _validate_segment_support(slide, payload)
        self.assertIn("车型甲", _ppt_narrative_text(slide, "2026-08")[1])
        wrong = deepcopy(slide)
        wrong["body_claims"][2]["claim"] = wrong["body_claims"][2]["claim"].replace("下降37.6%", "下降14.6%")
        with self.assertRaisesRegex(ValueError, "同比错配"):
            _validate_segment_support(wrong, payload)

    def test_long_body_is_rewritten_not_clipped_into_model_less_paragraph(self) -> None:
        slide, payload = self._supported_segment()
        slide["body_claims"][0]["claim"] += "不应通过删除最后的车型分析来解决正文过长的问题。" * 5
        with self.assertRaisesRegex(ValueError, "不能截掉车型段"):
            _validate_segment_support(slide, payload)

    def test_three_line_balance_keeps_every_clause_and_bounds_last_line(self) -> None:
        text = "8月级别表现出现分化，环比回升与同比下滑并存，不能把单月回升解读为全面恢复；" + \
               "累计结构中主流级别占比仍高，两端级别的变化需要分别观察，单月与累计不应混用；" + \
               "车型甲2.4万辆同比下降37.6%，车型乙2.2万辆同比增长14.6%，同级车型走势分化。"
        rendered = _wrap_business_text(text)
        self.assertEqual(len(rendered.splitlines()), 3)
        self.assertTrue(all(_display_width(line) <= 56.01 for line in rendered.splitlines()))
        self.assertEqual(rendered.replace("\n", ""), text.strip("，；。 "))

    def test_unknown_model_level_cannot_be_invented(self) -> None:
        slide, payload = self._supported_segment()
        slide["body_claims"][2]["claim"] = slide["body_claims"][2]["claim"].replace("车型乙", "A0级车型乙")
        with self.assertRaisesRegex(ValueError, "不能自行归类"):
            _validate_segment_support(slide, payload)

    def test_cumulative_share_cannot_use_single_month_value(self) -> None:
        slide, payload = self._supported_segment()
        payload["level_facts"] = [
            {"level": "B", "scope": "single_month", "share_pct": 36.5},
            {"level": "B", "scope": "year_to_date", "share_pct": 37.8},
        ]
        slide["body_claims"][1]["claim"] = "累计结构上B级份额36.5%，两端级别的市场份额增加，主流级别的占比收缩，单月回升与累计结构调整并存。"
        with self.assertRaisesRegex(ValueError, "份额错配"):
            _validate_segment_support(slide, payload)

    def test_overview_number_validation_rejects_numbers_missing_from_approved_slides(self) -> None:
        approved = [{
            "slide": 4,
            "headline": "1.2 零售量：8月销量155.6万辆同比降22.5%",
            "body_claims": [{"claim": "环比回升4.8%"}],
        }]
        overview = {"slides": [{
            "slide": 3,
            "headline": "概述：8月销量155.6万辆同比降22.5%",
            "body_claims": [{"claim": "累计同比下降19.6%"}],
        }]}
        with self.assertRaisesRegex(ValueError, "19.6"):
            _validate_overview_numbers(overview, approved, "2026-08")

    def test_deterministic_overview_only_reuses_accepted_numbers(self) -> None:
        approved = [
            {
                "slide": 4,
                "headline": "1.2 零售量：8月销量155.6万辆同比降22.5%",
                "body_claims": [{"claim": "环比回升4.8%"}],
                "anomaly": {"priority": 8, "fact_ids": ["P1.1-1"]},
            },
            {
                "slide": 17,
                "headline": "2.8 新能源：8月渗透率升至63.2%",
                "body_claims": [{"claim": "新能源销量98.2万辆"}],
                "anomaly": {"priority": 7, "fact_ids": ["P2-11.1"]},
            },
        ]
        overview = _deterministic_overview(approved, "2026-08")
        _validate_overview_numbers(overview, approved, "2026-08")
        self.assertEqual(overview["slides"][0]["slide"], 3)
        self.assertIn("155.6", overview["slides"][0]["headline"])


class MonthlyNarrativeRejectionTest(unittest.IsolatedAsyncioTestCase):
    async def test_failed_validation_never_persists_last_nonempty_candidate(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            examples = root / "examples.json"
            examples.write_text('{"pages": {}}', encoding="utf-8")
            run_dir = root / "test-reject"
            run_dir.mkdir()
            (run_dir / "evidence-B1.json").write_text('{"evidence": []}', encoding="utf-8")
            reply = SimpleNamespace(get_text_content=lambda: json.dumps({"slides": [{
                "slide": 4, "headline": "不应通过", "body_claims": [{"claim": "错误内容"}]}]}))
            agent = SimpleNamespace(reply=AsyncMock(return_value=reply))
            with patch("utils.monthly_report_narrative.BATCHES", ((4,),)), \
                 patch("utils.monthly_report_narrative.load_page_card_map", return_value={}), \
                 patch("utils.monthly_report_narrative._page_payload", return_value=[{
                     "slide": 4, "required_prefix": "1.2 零售量", "cards": [],
                 }]), \
                 patch("utils.monthly_report_narrative.build_monthly_narrative_agent", return_value=agent), \
                 patch("utils.monthly_report_narrative._validate_batch_facts", side_effect=ValueError("错误事实")), \
                 patch("utils.monthly_report_narrative.asyncio.sleep", new=AsyncMock()):
                with self.assertRaisesRegex(RuntimeError, "连续三次"):
                    await generate_monthly_narratives({"report_month": "2026-08", "cards": []},
                        run_id="test-reject", config={}, plugin_tools=[], mapping_path=root / "unused",
                        examples_path=examples, output_dir=root)
            self.assertEqual(agent.reply.await_count, 3)
            self.assertFalse((run_dir / "narrative-B1.json").exists())

    async def test_empty_cards_are_rejected_before_any_model_call_or_narrative_save(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            examples = root / "examples.json"
            examples.write_text('{"pages": {}}', encoding="utf-8")
            agent = SimpleNamespace(reply=AsyncMock())
            with patch("utils.monthly_report_narrative.BATCHES", ((4,),)), \
                 patch("utils.monthly_report_narrative.load_page_card_map", return_value={}), \
                 patch("utils.monthly_report_narrative.build_monthly_narrative_agent", return_value=agent) as factory:
                with self.assertRaisesRegex(RuntimeError, "最小事实包尚未具备可核验口径"):
                    await generate_monthly_narratives({"report_month": "2026-08", "cards": []},
                        run_id="test-preflight-empty", config={}, plugin_tools=[], mapping_path=root / "unused",
                        examples_path=examples, output_dir=root)
            factory.assert_not_called()
            agent.reply.assert_not_awaited()
            self.assertFalse(list((root / "test-preflight-empty").glob("narrative-*.json")))


if __name__ == "__main__":
    unittest.main()
