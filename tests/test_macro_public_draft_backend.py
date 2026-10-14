"""Opt-in draft publication guards. Fixtures are not real PPT acceptance."""
from __future__ import annotations

from copy import deepcopy
import asyncio
import hashlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Thread
from http.server import ThreadingHTTPServer
import unittest
from unittest.mock import patch
import urllib.error
import urllib.request

from utils.macro_report_jobs import MacroReportJobManager
from utils.macro_report_delivery import (
    DRAFT_GATES, formal_download_blocked, macro_evidence_fingerprint,
    verified_draft_artifact, verified_draft_state,
)


def request_payload(**values):
    return {"question": "生成2026年9月宏观经济月报", "report_month": "2026-09",
            "analysis_type": "macro_monthly_report", "capabilities": ["macro_monthly_report"],
            "model_provider": "minimax", "mcp_plugins": [], **values}


def draft_fixture(root, run_id):
    artifact = root / "outputs/report_公开数据草稿.pptx"
    artifact.parent.mkdir(parents=True)
    artifact.write_bytes(b"unit-fixture-not-a-real-pptx")
    sha = hashlib.sha256(artifact.read_bytes()).hexdigest()
    ledger = root / "working/ledger.json"
    ledger.parent.mkdir()
    ledger.write_text(json.dumps({"pptx_sha256": sha, "delivery_mode": "public_draft",
                                 "formal_delivery_allowed": False, "draft_content_complete": True}), encoding="utf-8")
    source = root / "working/data-package.json"
    source.write_text(json.dumps({"coverage": {"verified": 1}}), encoding="utf-8")
    pages = root / "working/macro-sources/pages"
    pages.mkdir(parents=True)
    (pages / "receipt.json").write_bytes(b"original public receipt")
    request = root / "inputs/request.json"
    request.parent.mkdir()
    request.write_text(json.dumps({"delivery_mode": "public_draft", "public_draft_confirmed": True}), encoding="utf-8")
    url = f"/api/macro-report/draft/{run_id}"
    state = {"run_id": run_id, "status": "draft_ready", "delivery_mode": "public_draft",
             "public_draft_confirmed": True, "formal_delivery_allowed": False,
             "draft_delivery_allowed": True, "business_status": "draft_passed",
             "validation": {"status": "passed"},
             "draft_validation": {"status": "passed", "artifact_sha256": sha},
             "artifact_validations": [{"validator": name, "path": "outputs/" + artifact.name,
                 "passed": True, "detail": {"artifact_sha256": sha}} for name in DRAFT_GATES],
             "draft_delivery": {"artifact_path": "outputs/" + artifact.name,
                 "artifact_sha256": sha, "ledger_path": "working/ledger.json",
                 "ledger_sha256": hashlib.sha256(ledger.read_bytes()).hexdigest(), "url": url,
                 "evidence_sha256": {relative: macro_evidence_fingerprint(root / relative, root)
                     for relative in ("working/data-package.json", "working/macro-sources/pages", "inputs/request.json")}}}
    result = {"answer": "公开数据草稿，未取证指标已留空，不是正式完整月报。", "run_id": run_id,
              "delivery_mode": "public_draft", "formal_delivery_allowed": False,
              "draft_delivery_allowed": True, "draft_delivery_url": url, "business_status": "draft_passed",
              "quality": {"overall_status": "草稿验收通过", "score": None, "formal_delivery_allowed": False},
              "skill_run": {"run_id": run_id, "delivery_mode": "public_draft", "delivery_url": url, "state": state}}
    return result, artifact, ledger


class DraftJobTest(unittest.TestCase):
    def test_default_uses_unified_template_retention(self):
        with TemporaryDirectory() as directory:
            manager = MacroReportJobManager(Path(directory), lambda *args: {})
            with patch.object(manager, "_spawn"):
                job = manager.start(request_payload())
            self.assertEqual(job["payload"]["delivery_mode"], "historical_retained")
            self.assertIs(job["payload"]["public_draft_confirmed"], False)

    def test_missing_or_string_consent_cannot_create_draft_job(self):
        with TemporaryDirectory() as directory:
            manager = MacroReportJobManager(Path(directory), lambda *args: {})
            for consent in (None, False, "true", 1):
                with self.subTest(consent=consent), self.assertRaisesRegex(ValueError, "显式"):
                    manager.start(request_payload(delivery_mode="public_draft", public_draft_confirmed=consent))
            self.assertEqual(list(Path(directory).glob("macro-*.json")), [])

    def test_mode_and_consent_persist_and_resume_unchanged(self):
        with TemporaryDirectory() as directory:
            manager = MacroReportJobManager(Path(directory), lambda *args: {})
            with patch.object(manager, "_spawn"):
                job = manager.start(request_payload(delivery_mode="public_draft", public_draft_confirmed=True))
            manager.update(job["run_id"], "sources", "来源检查点", 30, status="needs_repair")
            restored = MacroReportJobManager(Path(directory), lambda *args: {})
            with patch.object(restored, "_spawn"):
                resumed = restored.resume(job["run_id"])
            self.assertEqual(resumed["run_id"], job["run_id"])
            self.assertEqual(resumed["payload"]["delivery_mode"], "public_draft")
            self.assertIs(resumed["payload"]["public_draft_confirmed"], True)

    def test_valid_draft_is_terminal_without_promoting_formal(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            manager = MacroReportJobManager(root / "jobs", lambda *args: result)
            with patch.object(manager, "_spawn"):
                job = manager.start(request_payload(delivery_mode="public_draft", public_draft_confirmed=True))
            result, _, _ = draft_fixture(root / "run", job["run_id"])
            manager._run(job["run_id"])
            ready = manager.get(job["run_id"])
            self.assertEqual(ready["status"], "draft_ready")
            self.assertIs(ready["result"]["formal_delivery_allowed"], False)
            self.assertFalse(MacroReportJobManager.verified(result))
            with patch.object(manager, "_spawn") as spawn:
                manager.resume(job["run_id"])
                spawn.assert_not_called()

    def test_draft_result_cannot_complete_default_formal_job(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            manager = MacroReportJobManager(root / "jobs", lambda *args: result)
            with patch.object(manager, "_spawn"):
                job = manager.start(request_payload())
            result, _, _ = draft_fixture(root / "run", job["run_id"])
            manager._run(job["run_id"])
            self.assertEqual(manager.get(job["run_id"])["status"], "needs_repair")

    def test_foreign_run_draft_result_is_rejected(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            manager = MacroReportJobManager(root / "jobs", lambda *args: result)
            with patch.object(manager, "_spawn"):
                job = manager.start(request_payload(delivery_mode="public_draft", public_draft_confirmed=True))
            result, _, _ = draft_fixture(root / "run", "macro-20261004-100000-12345678")
            manager._run(job["run_id"])
            self.assertEqual(manager.get(job["run_id"])["status"], "needs_repair")


class DraftArtifactGuardTest(unittest.TestCase):
    def test_each_draft_gate_must_bind_same_artifact_sha(self):
        with TemporaryDirectory() as directory:
            result, _, _ = draft_fixture(Path(directory), "macro-20261004-100000-12345678")
            state = result["skill_run"]["state"]
            self.assertTrue(verified_draft_state(state, result["run_id"]))
            for name in DRAFT_GATES:
                modified = deepcopy(state)
                gate = next(item for item in modified["artifact_validations"] if item["validator"] == name)
                gate["detail"]["artifact_sha256"] = "b" * 64
                self.assertFalse(verified_draft_state(modified, result["run_id"]), name)
                gate["detail"].pop("artifact_sha256")
                self.assertFalse(verified_draft_state(modified, result["run_id"]), name)
            modified = deepcopy(state)
            modified["artifact_validations"] = [item for item in modified["artifact_validations"] if item["validator"] != "macro_draft_business"]
            modified["artifact_validations"].append({"validator": "macro_business", "passed": True})
            self.assertFalse(verified_draft_state(modified, result["run_id"]))

    def test_explicit_boundary_flags_cannot_be_forged_into_formal(self):
        with TemporaryDirectory() as directory:
            result, _, _ = draft_fixture(Path(directory), "macro-20261004-100000-12345678")
            state = result["skill_run"]["state"]
            for key, value in (("formal_delivery_allowed", True), ("delivery_mode", "formal"),
                               ("public_draft_confirmed", False), ("status", "completed"),
                               ("business_status", "passed")):
                self.assertFalse(verified_draft_state({**state, key: value}, result["run_id"]))

    def test_original_artifact_ledger_and_receipts_are_immutable(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            result, artifact, ledger = draft_fixture(root, "macro-20261004-100000-12345678")
            state = result["skill_run"]["state"]
            accepted = verified_draft_artifact(state, root, result["run_id"])
            self.assertEqual(accepted["path"], str(artifact.resolve()))
            for target in (artifact, ledger, root / "working/macro-sources/pages/receipt.json", root / "inputs/request.json"):
                original = target.read_bytes()
                target.write_bytes(b"changed")
                with self.assertRaises((ValueError, json.JSONDecodeError)):
                    verified_draft_artifact(state, root, result["run_id"])
                target.write_bytes(original)

    def test_missing_receipts_and_out_of_run_paths_are_rejected(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            result, _, _ = draft_fixture(root, "macro-20261004-100000-12345678")
            state = result["skill_run"]["state"]
            (root / "working/macro-sources/pages/receipt.json").unlink()
            with self.assertRaisesRegex(ValueError, "来源凭据"):
                verified_draft_artifact(state, root, result["run_id"])
            state["draft_delivery"]["artifact_path"] = "../foreign.pptx"
            for item in state["artifact_validations"]:
                item["path"] = "../foreign.pptx"
            with self.assertRaisesRegex(ValueError, "路径"):
                verified_draft_artifact(state, root, result["run_id"])


class DraftWebApiTest(unittest.TestCase):
    def test_executor_requires_consent_before_package_or_browser_actions(self):
        import app
        with patch.object(app.SKILL_REGISTRY, "get") as get_package:
            with self.assertRaisesRegex(app.MacroJobBlocked, "显式"):
                asyncio.run(app.run_macro_monthly_skill("公开草稿", {},
                    payload=request_payload(delivery_mode="public_draft")))
            get_package.assert_not_called()

    def test_executor_cannot_resume_formal_checkpoints_as_draft(self):
        import app
        with TemporaryDirectory() as directory:
            package = app.SKILL_REGISTRY.get("macro-monthly-report")
            run_id = "macro-20261004-100000-12345678"
            context = app.SkillRunContext(package, Path(directory), run_id=run_id)
            original = context.load_state()
            original["delivery_mode"] = "formal"
            context.save_state(original)
            with patch.object(app, "SKILL_RUNTIME_ROOT", Path(directory)), patch.object(app.SKILL_REGISTRY, "get", return_value=package), patch.object(app, "build_skill_runtime_tools") as tools:
                with self.assertRaisesRegex(app.MacroJobBlocked, "交付模式不同"):
                    asyncio.run(app.run_macro_monthly_skill("公开草稿", {}, run_id=run_id,
                        payload=request_payload(delivery_mode="public_draft", public_draft_confirmed=True)))
                tools.assert_not_called()
            self.assertEqual(context.load_state()["delivery_mode"], "formal")

    def test_dedicated_download_and_archive_keep_draft_boundary(self):
        import app
        with TemporaryDirectory() as directory:
            root = Path(directory)
            manager = MacroReportJobManager(root / "jobs", lambda *args: {})
            with patch.object(manager, "_spawn"):
                job = manager.start(request_payload(delivery_mode="public_draft", public_draft_confirmed=True))
            run_id = job["run_id"]
            run_root = root / "runtime/skill-runs" / run_id
            result, artifact, _ = draft_fixture(run_root, run_id)
            (run_root / "run-state.json").write_text(json.dumps(result["skill_run"]["state"]), encoding="utf-8")
            manager.update(run_id, "draft_ready", "草稿就绪", 100, status="draft_ready", result=result)
            with patch.object(app, "MACRO_REPORT_JOBS", manager), patch.object(app, "SKILL_RUNTIME_ROOT", run_root.parent), patch.object(app, "PROJECT_RUNS_FILE", root / "projects.json"):
                exported = app.verified_macro_draft_delivery(run_id)
                self.assertEqual(exported["path"], str(artifact.resolve()))
                with self.assertRaises(ValueError):
                    app.verified_macro_delivery(run_id)
                self.assertTrue(formal_download_blocked(run_id + "-copy.pptx", run_root.parent))
                project = app.store_project_run(result, "公开数据草稿", "macro_monthly_report", "minimax", run_id=run_id)
                self.assertEqual(project["status"], "草稿就绪")
                self.assertEqual(project["quality_status"], "草稿验收通过")
                self.assertEqual(project["business_status"], "draft_passed")
                self.assertIs(project["formal_delivery_allowed"], False)
                revised = app.update_project_run(project["id"], {"overall_status": "通过", "score": 100})
                self.assertEqual(revised["quality"]["overall_status"], "草稿验收通过")
                self.assertIsNone(revised["quality"]["score"])
                server = ThreadingHTTPServer(("127.0.0.1", 0), app.AgentDemoHandler)
                thread = Thread(target=server.serve_forever, daemon=True)
                thread.start()
                url = f"http://127.0.0.1:{server.server_port}/api/macro-report/draft/{run_id}"
                try:
                    with urllib.request.urlopen(url, timeout=5) as response:
                        self.assertEqual(response.status, 200)
                        self.assertEqual(response.read(), artifact.read_bytes())
                        self.assertIn("macro_public_draft.pptx", response.headers["Content-Disposition"])
                    artifact.write_bytes(b"changed")
                    with self.assertRaises(urllib.error.HTTPError) as error:
                        urllib.request.urlopen(url, timeout=5)
                    self.assertEqual(error.exception.code, 409)
                finally:
                    server.shutdown()
                    server.server_close()
                    thread.join(2)


if __name__ == "__main__":
    unittest.main()
