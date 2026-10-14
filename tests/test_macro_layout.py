"""Macro-only layout gate tests; Office calls are replaced, never fake live QA."""
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

SCRIPTS = Path(__file__).resolve().parents[1] / "skills/macro-monthly-report/scripts"
sys.path.insert(0, str(SCRIPTS))
spec = importlib.util.spec_from_file_location("macro_layout_validator", SCRIPTS / "validate_macro_layout.py")
layout = importlib.util.module_from_spec(spec)
spec.loader.exec_module(layout)


class LayoutGateTests(unittest.TestCase):
    def test_runtime_working_cwd_uses_declared_skill_run_root(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "working").mkdir()
            (root / "outputs").mkdir()
            artifact = root / "outputs/report.pptx"
            artifact.write_bytes((SCRIPTS.parent / "assets/reference.pptx").read_bytes())
            def timeout(*args, **kwargs):
                raise subprocess.TimeoutExpired("powershell.exe", kwargs["timeout"])
            with patch.dict(layout.os.environ, {"SKILL_RUN_ROOT": str(root)}), patch.object(layout.Path, "cwd", return_value=root / "working"):
                result = layout.validate_layout("outputs/report.pptx", "working/layout.json", runner=timeout)
            self.assertEqual(result["artifact_path"], str(artifact.resolve()))
            self.assertEqual(result["full_report"], str((root / "working/layout.json").resolve()))
            self.assertEqual(len(result["artifact_sha256"]), 64)
            self.assertFalse(result["passed"])  # Timeout remains a genuine failure.

    def test_wrapper_timeout_is_not_pass_and_persists_sha(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            report = root / "working/layout.json"
            # Use the read-only macro asset, copied into the isolated test root.
            artifact = root / "report.pptx"
            artifact.write_bytes((SCRIPTS.parent / "assets/reference.pptx").read_bytes())
            def timeout(*args, **kwargs):
                raise subprocess.TimeoutExpired("powershell.exe", kwargs["timeout"])
            result = layout.validate_layout("report.pptx", "working/layout.json", run_root=root, runner=timeout)
            self.assertFalse(result["passed"])
            self.assertEqual(result["status"], "unavailable")
            self.assertEqual(len(result["artifact_sha256"]), 64)
            self.assertFalse(json.loads(report.read_text(encoding="utf-8"))["passed"])

    def test_wrapper_outside_input_path_is_not_pass(self):
        with tempfile.TemporaryDirectory() as directory:
            result = layout.validate_layout("../outside.pptx", "working/layout.json", run_root=directory)
            self.assertFalse(result["passed"])
            self.assertIn("outside_run_root", result["issues"][0]["detail"])
            with self.assertRaises(ValueError):
                layout.workspace_path("../outside.json", directory)

    def test_scope_selects_data_text_not_invisible_decoration(self):
        deck = layout.Presentation(str(SCRIPTS.parent / "assets/reference.pptx"))
        scope = layout.build_scope(deck, "fixturehash")
        targets = {(item["slide"], item["shape_id"]): item["role"] for item in scope["targets"]}
        self.assertEqual(targets[(4, 19)], "body")
        self.assertEqual(targets[(4, 6)], "caption")
        self.assertEqual(targets[(8, 24)], "caption")
        self.assertEqual(targets[(28, 9)], "caption")
        self.assertEqual(targets[(30, 17)], "caption")
        self.assertEqual(targets[(32, 6)], "body")
        self.assertNotIn((31, 10), targets)  # Intentional empty background card.
        self.assertNotIn((7, 3), targets)  # Decorative slide-number footer.
        self.assertNotIn((1, 18), targets)  # Cover is not a macro data page.
        cells = [item for item in scope["targets"] if item["kind"] == "table_cell"]
        self.assertTrue(cells)
        self.assertTrue(all(item["slide"] in {7, 32} for item in cells))

    def test_actual_bounds_detect_overflow_and_chart_overlap(self):
        target = {"slide": 10, "shape_id": 6, "role": "body", "kind": "text"}
        scope = {"artifact_sha256": "x", "measurement_id": "one", "targets": [target], "issues": []}
        raw = {"success": True, "office_passed": True, "slides": 33, "rendered": 33, "roundtrip_slides": 33,
               "artifact_sha256": "x", "measurement_id": "one", "slide_width": 960, "slide_height": 540,
               "issues": [], "measurements": [{**target, "measured": True, "visible": True, "rotation": 0, "text": "业务主旨句",
                   "text_box": {"x": 20, "y": 20, "width": 500, "height": 50, "margin_left": 0, "margin_right": 0, "margin_top": 0, "margin_bottom": 0},
                   "rendered_bounds": {"x": 20, "y": 20, "width": 500, "height": 75}}],
               "obstacles": [{"slide": 10, "shape_id": 7, "kind": "chart", "box": {"x": 20, "y": 80, "width": 500, "height": 300}}]}
        result = layout.audit_measurements(raw, scope)
        self.assertFalse(result["passed"])
        self.assertEqual({item["code"] for item in result["issues"]}, {"text_box_overflow", "text_overlaps_chart"})
        raw["measurements"][0]["rendered_bounds"]["height"] = 48
        self.assertTrue(layout.audit_measurements(raw, scope)["passed"])

    def test_measurements_cannot_omit_a_required_slot_or_reuse_audit(self):
        scope = {"artifact_sha256": "x", "measurement_id": "current", "targets": [{"slide": 4, "shape_id": 19}], "issues": []}
        result = layout.audit_measurements({"success": True, "artifact_sha256": "x", "measurement_id": "old", "measurements": []}, scope)
        self.assertFalse(result["passed"])
        self.assertIn("layout_measurement_invocation_mismatch", {item["code"] for item in result["issues"]})
        self.assertIn("required_text_measurement_missing", {item["code"] for item in result["issues"]})


if __name__ == "__main__":
    unittest.main()
