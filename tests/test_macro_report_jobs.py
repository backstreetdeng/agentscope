from __future__ import annotations

import json
import hashlib
from pathlib import Path
import tempfile
from threading import Thread
from http.server import ThreadingHTTPServer
import unittest
from unittest.mock import patch
import urllib.request

from utils.macro_report_jobs import MacroJobBlocked, MacroReportJobManager


def payload() -> dict:
    return {"question": "生成2026年9月宏观经济月报", "report_month": "2026-09",
            "analysis_type": "macro_monthly_report", "capabilities": ["macro_monthly_report"],
            "model_provider": "minimax", "mcp_plugins": []}


def verified_result() -> dict:
    return {"answer": "已验收", "business_status": "passed", "formal_delivery_allowed": True,
            "skill_run": {"delivery_url": "/outputs/ppt/test.pptx", "state": {
                "business_status": "passed", "formal_delivery_allowed": True,
                "validation": {"status": "passed"}, "artifact_validations": [
                    {"validator": name, "passed": True} for name in
                    ("macro_business", "pptx_structure", "powerpoint_render", "macro_layout")]}}}


class MacroReportJobsTest(unittest.TestCase):
    def test_immediate_submission_persists_safe_input_and_run_id(self):
        with tempfile.TemporaryDirectory() as directory:
            manager = MacroReportJobManager(Path(directory), lambda *args: {})
            submitted = dict(payload(), api_key="must-not-persist")
            with patch.object(manager, "_spawn"):
                job = manager.start(submitted)
            self.assertRegex(job["run_id"], r"^macro-\d{8}-\d{6}-[a-f0-9]{8}$")
            stored = json.loads((Path(directory) / f"{job['run_id']}.json").read_text(encoding="utf-8"))
            self.assertEqual(stored["status"], "queued")
            self.assertNotIn("api_key", stored["payload"])
            restored = MacroReportJobManager(Path(directory), lambda *args: {}).get(job["run_id"])
            self.assertEqual(restored["payload"]["report_month"], "2026-09")

    def test_real_gate_evidence_is_required_not_only_model_prose(self):
        with tempfile.TemporaryDirectory() as directory:
            result = verified_result()
            result["skill_run"]["state"]["artifact_validations"] = []
            manager = MacroReportJobManager(Path(directory), lambda *args: result)
            with patch.object(manager, "_spawn"):
                job = manager.start(payload())
            manager._run(job["run_id"])
            self.assertEqual(manager.get(job["run_id"])["status"], "needs_repair")

    def test_layout_gate_is_required_even_when_other_gates_pass(self):
        result=verified_result()
        result["skill_run"]["state"]["artifact_validations"]=[
            item for item in result["skill_run"]["state"]["artifact_validations"]
            if item["validator"] != "macro_layout"]
        self.assertFalse(MacroReportJobManager.verified(result))

    def test_unsupported_scope_rejected_before_a_background_job_exists(self):
        with tempfile.TemporaryDirectory() as directory:
            manager=MacroReportJobManager(Path(directory),lambda *args: {})
            for request in [dict(payload(),mode="unsupported"),dict(payload(),slides=[4])]:
                with self.assertRaisesRegex(ValueError,"仅支持完整预测版"):
                    manager.start(request)
            self.assertEqual(list(Path(directory).glob("macro-*.json")),[])

    def test_success_is_archived_and_completed_only_after_all_gates(self):
        with tempfile.TemporaryDirectory() as directory:
            manager = MacroReportJobManager(Path(directory), lambda *args: verified_result(),
                                            lambda run_id, request, result: {"id": run_id})
            with patch.object(manager, "_spawn"):
                job = manager.start({**payload(),"mode":"forecast","delivery_mode":"formal"})
            manager._run(job["run_id"])
            finished = manager.get(job["run_id"])
            self.assertEqual(finished["status"], "completed")
            self.assertFalse(finished["recoverable"])
            self.assertEqual(finished["result"]["project"]["id"], job["run_id"])
            self.assertIn("archive", finished["completed_phases"])

    def test_source_failure_preserves_progress_and_exact_issues(self):
        def execute(manager, run_id, _request):
            manager.checkpoint(run_id, "inventory", {"path": "contract.json"})
            manager.update(run_id, "sources", "正在检索", 29)
            manager.checkpoint(run_id, "sources", {"verified": 3}, completed=False)
            raise MacroJobBlocked("PMI来源读取失败", issues=[{"request_id": "pmi", "code": "timeout"}])

        with tempfile.TemporaryDirectory() as directory:
            manager = MacroReportJobManager(Path(directory), execute)
            with patch.object(manager, "_spawn"):
                job = manager.start(payload())
            manager._run(job["run_id"])
            failed = manager.get(job["run_id"])
            self.assertEqual(failed["status"], "needs_repair")
            self.assertEqual(failed["phase"], "sources")
            self.assertEqual(failed["error"]["issues"][0]["request_id"], "pmi")
            self.assertEqual(failed["checkpoints"]["sources"]["verified"], 3)
            self.assertNotIn("sources", failed["completed_phases"])
            with patch.object(manager, "_spawn"):
                resumed = manager.resume(job["run_id"])
            self.assertEqual(resumed["run_id"], failed["run_id"])
            self.assertEqual(resumed["checkpoints"], failed["checkpoints"])

    def test_cancelled_run_keeps_checkpoints_and_can_resume(self):
        with tempfile.TemporaryDirectory() as directory:
            manager = MacroReportJobManager(Path(directory), lambda *args: verified_result())
            with patch.object(manager, "_spawn"):
                job = manager.start(payload())
                manager.checkpoint(job["run_id"], "inventory", {"contract": "saved"})
                manager.cancel(job["run_id"])
            manager._run(job["run_id"])
            self.assertEqual(manager.get(job["run_id"])["status"], "cancelled")
            with patch.object(manager, "_spawn"):
                resumed = manager.resume(job["run_id"])
            self.assertEqual(resumed["status"], "queued")
            self.assertIn("inventory", resumed["completed_phases"])

    def test_restart_only_recovers_nonterminal_tasks(self):
        with tempfile.TemporaryDirectory() as directory:
            manager = MacroReportJobManager(Path(directory), lambda *args: verified_result())
            with patch.object(manager, "_spawn"):
                pending = manager.start(payload())
                terminal = manager.start(payload())
            manager.update(terminal["run_id"], "sources", "需补来源", 22, status="needs_repair")
            restored = MacroReportJobManager(Path(directory), lambda *args: verified_result())
            with patch.object(restored, "_spawn") as spawn:
                restored.recover_pending()
                spawn.assert_called_once_with(pending["run_id"])
            self.assertEqual(restored.get(terminal["run_id"])["status"], "needs_repair")

    def test_invalid_month_and_future_cutoff_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            manager = MacroReportJobManager(Path(directory), lambda *args: {})
            with self.assertRaises(ValueError):
                manager.start(dict(payload(), report_month="2026-13"))
            with self.assertRaises(ValueError):
                manager.start(dict(payload(), cutoff_date="2099-01-01"))

    def test_frontend_routes_macro_to_durable_job_and_recovers_same_run(self):
        code = (Path(__file__).resolve().parents[1] / "assets/strategy-analysis.js").read_text(encoding="utf-8")
        self.assertIn('if (monthlyEnabled || macroEnabled)', code)
        self.assertIn('const ACTIVE_MACRO_RUN_KEY', code)
        self.assertIn('"/api/macro-report/jobs"', code)
        self.assertIn('backgroundJobApi(runId)', code)
        self.assertIn('"waiting_input", "needs_repair"', code)
        self.assertIn('syncMacroRunConfig();', code)


class MacroReportApiTest(unittest.TestCase):
    def test_chat_returns_run_id_and_status_resume_are_same_job(self):
        import app
        with tempfile.TemporaryDirectory() as directory:
            manager = MacroReportJobManager(Path(directory), lambda *args: {})
            server = ThreadingHTTPServer(("127.0.0.1", 0), app.AgentDemoHandler)
            server_thread = Thread(target=server.serve_forever, daemon=True)
            server_thread.start()
            base = f"http://127.0.0.1:{server.server_port}"

            def request(path, value=None):
                data = json.dumps(value).encode() if value is not None else None
                req = urllib.request.Request(base + path, data=data, headers={"Content-Type": "application/json"})
                with urllib.request.urlopen(req, timeout=5) as response:
                    return response.status, json.loads(response.read())

            try:
                with patch.object(app, "MACRO_REPORT_JOBS", manager), patch.object(manager, "_spawn"), patch.object(app, "_macro_execution_config", return_value={"active_provider": "minimax"}):
                    status, submitted = request("/api/chat", payload())
                    self.assertEqual(status, 202)
                    run_id = submitted["run_id"]
                    _, snapshot = request("/api/macro-report/jobs/" + run_id)
                    self.assertEqual(snapshot["run_id"], run_id)
                    _, cancelled = request("/api/macro-report/jobs/cancel", {"run_id": run_id})
                    self.assertEqual(cancelled["phase"], "cancel")
                    manager.update(run_id, "cancelled", "取消", 1, status="cancelled")
                    _, resumed = request("/api/macro-report/jobs/resume", {"run_id": run_id})
                    self.assertEqual(resumed["run_id"], run_id)
                    self.assertEqual(resumed["status"], "queued")
            finally:
                server.shutdown()
                server.server_close()
                server_thread.join(2)

    def test_export_rejects_old_baseline_and_accepts_only_verified_same_run(self):
        import app
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            manager = MacroReportJobManager(root / "jobs", lambda *args: verified_result())
            with patch.object(manager, "_spawn"):
                submitted = manager.start(payload())
            run_id = submitted["run_id"]
            report = root / "outputs/ppt" / f"{run_id}-宏观月报.pptx"
            report.parent.mkdir(parents=True)
            report.write_bytes(b"verified-test-file")
            result = verified_result()
            result["skill_run"]["delivery_url"] = "/outputs/ppt/" + report.name
            state_path = root / "runtime/skill-runs" / run_id / "run-state.json"
            state_path.parent.mkdir(parents=True)
            original = state_path.parent / "outputs/report.pptx"
            original.parent.mkdir()
            original.write_bytes(report.read_bytes())
            fingerprint = hashlib.sha256(report.read_bytes()).hexdigest()
            ledger = state_path.parent / "working/ledger.json"
            ledger.parent.mkdir()
            ledger.write_text(json.dumps({"pptx_sha256": fingerprint}), encoding="utf-8")
            state = result["skill_run"]["state"]
            for item in state["artifact_validations"]:
                item["path"] = "outputs/report.pptx"
            state["delivery"] = {"artifact_path": "outputs/report.pptx", "artifact_sha256": fingerprint,
                                 "published_sha256": fingerprint, "published_filename": report.name,
                                 "url": result["skill_run"]["delivery_url"], "ledger_path": "working/ledger.json",
                                 "ledger_sha256": hashlib.sha256(ledger.read_bytes()).hexdigest()}
            state_path.write_text(json.dumps(state), encoding="utf-8")
            manager.update(run_id, "completed", "完成", 100, status="completed", result=result)
            with patch.object(app, "MACRO_REPORT_JOBS", manager), patch.object(app, "PROJECT_DIR", root), patch.object(app, "PPT_OUTPUT_DIR", report.parent), patch.object(app, "SKILL_RUNTIME_ROOT", root / "runtime/skill-runs"):
                with self.assertRaises(ValueError):
                    app.verified_macro_delivery("skill-20261003-152013-a6da7bb1")
                exported = app.verified_macro_delivery(run_id)
                self.assertEqual(exported["run_id"], run_id)
                self.assertEqual(exported["pptx_url"], result["skill_run"]["delivery_url"])
                self.assertEqual(exported["sha256"], fingerprint)
                report.write_bytes(b"tampered-test-file")
                with self.assertRaisesRegex(ValueError, "指纹"):
                    app.verified_macro_delivery(run_id)
                report.write_bytes(original.read_bytes())
                original.write_bytes(b"tampered-original")
                with self.assertRaisesRegex(ValueError, "指纹"):
                    app.verified_macro_delivery(run_id)
                original.write_bytes(report.read_bytes())
                ledger.write_text(json.dumps({"pptx_sha256": "0" * 64}), encoding="utf-8")
                with self.assertRaisesRegex(ValueError, "指纹"):
                    app.verified_macro_delivery(run_id)
                ledger.write_text(json.dumps({"pptx_sha256": fingerprint}), encoding="utf-8")
                state["formal_delivery_allowed"] = False
                state_path.write_text(json.dumps(state), encoding="utf-8")
                with self.assertRaises(ValueError):
                    app.verified_macro_delivery(run_id)

    def test_resumed_archive_updates_existing_project_without_duplicate(self):
        import app
        with tempfile.TemporaryDirectory() as directory:
            with patch.object(app, "PROJECT_RUNS_FILE", Path(directory) / "projects.json"):
                blocked = {**verified_result(), "business_status": "incomplete", "formal_delivery_allowed": False}
                first = app.store_project_run(blocked, "月报", "macro_monthly_report", "minimax", run_id="macro-test")
                finished = app.store_project_run(verified_result(), "月报", "macro_monthly_report", "minimax", run_id="macro-test", replace_existing=True)
                self.assertEqual(first["id"], finished["id"])
                self.assertEqual(finished["status"], "已完成")
                self.assertEqual(len(json.loads(app.PROJECT_RUNS_FILE.read_text(encoding="utf-8"))), 1)


if __name__ == "__main__":
    unittest.main()
