"""Actual web executor must enable cross-run evidence reuse, not just document it."""
import asyncio
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, patch

from utils.macro_report_jobs import MacroReportJobManager


class MacroReuseBackendTest(unittest.TestCase):
    def test_web_source_phase_supplies_archive_and_persists_real_progress(self):
        import app
        with TemporaryDirectory() as directory:
            archive = Path(directory) / "skill-runs"
            manager = MacroReportJobManager(Path(directory) / "jobs", lambda *args: {})
            payload = {"question": "生成2026年9月宏观经济月报", "report_month": "2026-09",
                       "cutoff_date": "2026-10-05", "model_provider": "minimax"}
            with patch.object(manager, "_spawn"):
                job = manager.start(payload)
            run_id = job["run_id"]
            requests = [{"id": "test-indicator"}]

            def runtime_tools(context):
                async def call(relative, arguments, timeout):
                    self.assertEqual(relative, "scripts/inspect_macro_template.py")
                    context.workspace_path("working/template-contract.json").write_text(
                        json.dumps({"source_requests": requests}), encoding="utf-8")
                    return None  # The response envelope alone is mocked below.
                return [SimpleNamespace(name="skill_run_script", call=call)]

            async def collect(month, cutoff, current_requests, root, **options):
                self.assertEqual(month, "2026-09")
                self.assertEqual(cutoff, "2026-10-05")
                self.assertEqual(current_requests, requests)
                self.assertEqual(options["reuse_root"], archive)
                self.assertEqual(root, archive / run_id)
                options["progress"]("同月指标续跑：复用 0/1 项，仅补跑 1 项", 10)
                return {"status": "blocked", "coverage": {"verified": 0},
                        "source_reuse": {"enabled": True, "reused": 0, "pending": 1},
                        "issues": [{"request_id": "test-indicator", "message": "test source gap"}]}

            collector = AsyncMock(side_effect=collect)
            module = SimpleNamespace(collect_sources=collector)
            spec = SimpleNamespace(loader=SimpleNamespace(exec_module=lambda item: None))
            with patch.object(app, "SKILL_RUNTIME_ROOT", archive), \
                 patch.object(app, "build_skill_runtime_tools", side_effect=runtime_tools), \
                 patch.object(app, "_skill_chunk_json", return_value={"success": True}), \
                 patch("importlib.util.spec_from_file_location", return_value=spec), \
                 patch("importlib.util.module_from_spec", return_value=module), \
                 patch.object(app, "record_tool_call"):
                with self.assertRaises(app.MacroJobBlocked):
                    asyncio.run(app.run_macro_monthly_skill(payload["question"], {},
                        run_id=run_id, jobs=manager, payload=payload))

            collector.assert_awaited_once()
            saved = json.loads((archive / run_id / "working/data-package.json").read_text(encoding="utf-8"))
            self.assertTrue(saved["source_reuse"]["enabled"])
            self.assertEqual(saved["source_reuse"]["pending"], 1)
            messages = [event["message"] for event in manager.get(run_id)["events"]]
            self.assertTrue(any("同月指标续跑" in message for message in messages))
            state = json.loads((archive / run_id / "run-state.json").read_text(encoding="utf-8"))
            self.assertEqual(state["status"], "needs_repair")
            self.assertFalse(state["formal_delivery_allowed"])


if __name__ == "__main__":
    unittest.main()
