from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from utils.macro_report_delivery import baseline_delivery, formal_download_blocked, verified_office_measurement, office_measurement_payload, macro_evidence_fingerprint


class MacroDeliveryTest(unittest.TestCase):
    def delivery(self):
        return baseline_delivery("2026-09", {
            "report_month": "2026-09", "data_boundary": "模板内嵌历史可编辑数据",
            "summary": {"slides": 33, "charts": 37, "tables": 1},
        })

    def test_baseline_never_claims_current_authoritative_research(self):
        result = self.delivery()
        self.assertIn("未检索", result["answer"])
        self.assertIn("原模板正文", result["answer"])
        self.assertEqual(result["business_status"], "incomplete")
        self.assertEqual(result["quality"]["overall_status"], "阻断")
        self.assertFalse(result["formal_delivery_allowed"])
        self.assertIsNone(result["quality"]["score"])

    def test_delivery_rejects_mismatched_ledger_month(self):
        with self.assertRaisesRegex(ValueError, "月份"):
            baseline_delivery("2026-09", {"report_month": "2026-08"})

    def test_structural_pass_does_not_promote_baseline_project(self):
        import app
        result = {**self.delivery(), "skill_run": {"state": {
            "status": "completed", "validation": {"status": "passed"},
        }}}
        with TemporaryDirectory() as directory:
            with patch.object(app, "PROJECT_RUNS_FILE", Path(directory) / "projects.json"):
                stored = app.store_project_run(result, "生成月报", "macro_monthly_report", "minimax")
                self.assertEqual(stored["status"], "部分完成")
                self.assertEqual(stored["quality_status"], "阻断")
                updated = app.update_project_run(stored["id"], {"overall_status": "通过", "score": 100})
                self.assertEqual(updated["quality_status"], "阻断")
                self.assertIsNone(updated["quality"]["score"])

    def test_frontend_prefers_server_business_gate(self):
        source = (Path(__file__).resolve().parents[1] / "assets/strategy-analysis.js").read_text(encoding="utf-8")
        self.assertIn("const quality = draftDelivery.isDraft ?", source)
        self.assertIn("} : serverQuality || (skillRun ?", source)
        self.assertIn("data.score != null", source)

    def test_cached_download_is_blocked_without_affecting_other_artifacts(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            run_id = "skill-20261003-152013-a6da7bb1"
            (root / run_id).mkdir()
            (root / run_id / "run-state.json").write_text(json.dumps({"formal_delivery_allowed": False}), encoding="utf-8")
            self.assertTrue(formal_download_blocked(run_id + "-月报.pptx", root))
            self.assertFalse(formal_download_blocked("其他报告.pptx", root))


class OfficeMeasurementBindingTest(unittest.TestCase):
    def evidence(self):
        return {"office_passed": True, "passed": True,
                "artifact_sha256": "a" * 64, "validated_at": "2026-10-03T10:00:00Z",
                "slides": 33, "rendered": 33, "roundtrip_slides": 33}

    def test_successful_same_file_same_invocation_passes(self):
        self.assertTrue(verified_office_measurement({"success": True}, self.evidence(), self.evidence(), "a" * 64))

    def test_failed_subprocess_cannot_use_valid_looking_json(self):
        self.assertFalse(verified_office_measurement({"success": False}, self.evidence(), self.evidence(), "a" * 64))

    def test_old_or_different_file_report_is_rejected(self):
        for update in ({"artifact_sha256": "b" * 64}, {"validated_at": "previous"}, {"office_passed": False}):
            with self.subTest(update=update):
                report = {**self.evidence(), **update}
                self.assertFalse(verified_office_measurement({"success": True}, self.evidence(), report, "a" * 64))

    def test_missing_timestamp_or_incomplete_pages_are_rejected(self):
        for update in ({"validated_at": None}, {"rendered": 32}, {"roundtrip_slides": 0}, {"slides": 32}):
            with self.subTest(update=update):
                payload = {**self.evidence(), **update}
                self.assertFalse(verified_office_measurement({"success": True}, payload, payload, "a" * 64))

    def test_office_open_pass_does_not_hide_separate_layout_failure(self):
        report = {**self.evidence(), "passed": False, "issues": [{"code": "text_overflow"}]}
        self.assertTrue(verified_office_measurement({"success": True}, report, report, "a" * 64))
        self.assertFalse(report["passed"])

    def test_stdout_payload_accepts_pretty_json_or_log_then_final_json(self):
        for stdout in (json.dumps(self.evidence(), indent=2), 'progress\n' + json.dumps(self.evidence())):
            self.assertEqual(office_measurement_payload({"stdout": stdout}), self.evidence())

    def test_absent_or_nonobject_stdout_cannot_reuse_saved_report(self):
        for stdout in ('', 'crashed', '[1,2]', 'null'):
            payload = office_measurement_payload({"stdout": stdout})
            self.assertEqual(payload, {})
            self.assertFalse(verified_office_measurement({"success": True}, payload, self.evidence(), "a" * 64))


class SourceEvidenceFingerprintTest(unittest.TestCase):
    def test_source_receipts_add_delete_rename_and_content_changes_invalidate(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            pages = root / "pages"
            pages.mkdir()
            receipt = pages / "source-one.json"
            receipt.write_bytes(b"original source body")
            original = macro_evidence_fingerprint(pages, root)
            self.assertEqual(original, macro_evidence_fingerprint(pages, root))
            receipt.write_bytes(b"altered source body")
            self.assertNotEqual(original, macro_evidence_fingerprint(pages, root))
            receipt.write_bytes(b"original source body")
            additional = pages / "source-two.json"
            additional.write_bytes(b"new")
            self.assertNotEqual(original, macro_evidence_fingerprint(pages, root))
            additional.unlink()
            renamed = pages / "renamed.json"
            receipt.rename(renamed)
            self.assertNotEqual(original, macro_evidence_fingerprint(pages, root))
            renamed.unlink()
            self.assertNotEqual(original, macro_evidence_fingerprint(pages, root))
            pages.rmdir()
            self.assertIsNone(macro_evidence_fingerprint(pages, root))

    def test_file_hash_and_out_of_run_paths(self):
        with TemporaryDirectory() as directory, TemporaryDirectory() as outside:
            root = Path(directory)
            receipt = root / "receipt.json"
            receipt.write_bytes(b"source")
            self.assertEqual(len(macro_evidence_fingerprint(receipt, root)), 64)
            with self.assertRaises(ValueError):
                macro_evidence_fingerprint(Path(outside), root)


if __name__ == "__main__":
    unittest.main()
