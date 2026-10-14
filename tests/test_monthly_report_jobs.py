from __future__ import annotations

import tempfile
import unittest
import json
from pathlib import Path
from unittest.mock import patch

import app


def ready_package() -> dict:
    cards = []
    for code in app.MONTHLY_REPORT_BROWSER._assess_snapshot("")["missing_cards"]:
        if code in {"P1.1-2", "P1.2-2B", "P1.2-2D"}:
            text = f"{code}：月表\n08\n123"
        elif code in {"P1.2-3A", "P1.2-3B"}:
            text = f"{code}：当前快照\n企业\n123"
        else:
            text = f"{code}：累计\n2026\n123"
        cards.append({"code": code, "text": text})
    return {
        "code": "data_package_ready",
        "generation_ready": True,
        "report_month": "2026-08",
        "cards_expected": 45,
        "cards_usable": 45,
        "snapshot_path": "E:/AI/data/envs/helloagent/myproject/outputs/monthly-report-data/test.json",
        "cards": cards,
        "source_url": app.MONTHLY_REPORT_BROWSER.source_url,
    }


def ready_narrative(run_id: str) -> dict:
    slides = []
    for page in (3, 4, 5, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19):
        slides.append({
            "slide": page,
            "headline": f"第{page}页已校验主旨句",
            "headline_evidence_ids": [],
            "anomaly": {"type": "ordinary_change", "priority": 5, "fact_ids": ["P1.1-1"]},
            "body_claims": [],
        })
    return {"run_id": run_id, "report_month": "2026-08", "slides": slides, "evidence": [],
            "research": {"status": "completed", "nodes": []},
            "narrative_rule_version": app.NARRATIVE_RULE_VERSION, "path": "narrative.json"}


class MonthlyReportJobManagerTest(unittest.TestCase):
    def make_manager(self, directory: str) -> app.MonthlyReportJobManager:
        return app.MonthlyReportJobManager(Path(directory))

    @staticmethod
    def payload() -> dict:
        return {
            "question": "生成乘用车月报",
            "analysis_type": "passenger_car_monthly_report",
            "model_provider": "minimax",
            "capabilities": ["passenger_car_monthly_report"],
            "mcp_plugins": [],
        }

    def test_package_loader_binds_actual_read_path_not_embedded_path(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            path = root / "outputs/monthly-report-data/copied.json"
            path.parent.mkdir(parents=True)
            path.write_text(json.dumps({"cards": [], "snapshot_path": "wrong-or-stale.json"}), encoding="utf-8")
            with patch("app.PROJECT_DIR", root):
                loaded = app.MonthlyReportJobManager._load_package(str(path))
            self.assertEqual(loaded["snapshot_path"], str(path))
            self.assertEqual(json.loads(path.read_text(encoding="utf-8"))["snapshot_path"], "wrong-or-stale.json")

    def test_run_id_is_persisted_and_reloadable(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            manager = self.make_manager(directory)
            with patch.object(manager, "_spawn"):
                created = manager.start(self.payload())
            self.assertRegex(created["run_id"], r"^month-\d{8}-\d{6}-[0-9a-f]{8}$")
            self.assertTrue((Path(directory) / f"{created['run_id']}.json").is_file())
            reloaded = self.make_manager(directory).get(created["run_id"])
            self.assertIsNotNone(reloaded)
            self.assertEqual(reloaded["payload"]["analysis_type"], "passenger_car_monthly_report")

    def test_background_workflow_completes_with_real_phase_events(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            manager = self.make_manager(directory)
            with patch.object(manager, "_spawn"):
                created = manager.start(self.payload())
            package = ready_package()

            def run_step(_run_id, phase, _progress, _description, _factory, max_attempts=2, **kwargs):
                del max_attempts, kwargs
                manager._update(_run_id, phase, "running", _description, _progress)
                if phase == "preflight":
                    return {"page_ready": True, "code": "ready", "report_month": "2026-08"}
                if phase == "data_collect":
                    return package
                if phase == "narrative":
                    return {"narrative": ready_narrative(_run_id), "mcp_plugins": {}, "tool_events": []}
                raise AssertionError(f"unexpected phase: {phase}")

            project = {"id": "project-1", "title": "乘用车月报", "created_at": "2026-09-29T10:00:00"}
            with (
                patch.object(manager, "_run_async_step", side_effect=run_step),
                patch("app.store_project_run", return_value=project),
                patch("app.project_list_item", return_value={"id": "project-1", "title": "乘用车月报"}),
                patch("app.store_latest_agent_run"),
            ):
                manager._run(created["run_id"])

            finished = manager.get(created["run_id"])
            self.assertEqual(finished["status"], "completed")
            self.assertEqual(finished["progress"], 100)
            self.assertFalse(finished["recoverable"])
            self.assertIn("preflight", finished["completed_phases"])
            self.assertIn("data_collect", finished["completed_phases"])
            self.assertIn("data_gate", finished["completed_phases"])
            self.assertIn("narrative", finished["completed_phases"])
            self.assertIn("archive", finished["completed_phases"])
            phases = [event["phase"] for event in finished["events"]]
            self.assertIn("data_collect", phases)
            self.assertEqual(phases[-1], "completed")

    def test_resume_validates_data_and_narrative_without_live_browser(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            manager = self.make_manager(directory)
            with patch.object(manager, "_spawn"):
                created = manager.start(self.payload())
            run_id = created["run_id"]
            manager._save_checkpoint(run_id, "preflight", {"page_ready": True, "code": "ready"})
            manager._save_checkpoint(run_id, "data_collect", {"snapshot_path": "checkpoint.json"})
            manager._save_checkpoint(run_id, "narrative", {"path": "narrative.json"})
            package = ready_package()
            narrative = ready_narrative(run_id)
            project = {"id": "project-2", "title": "恢复后的月报", "created_at": "2026-09-29T10:00:00"}

            with (
                patch.object(manager, "_run_async_step", return_value={"page_ready": True, "report_month": "2026-08"}) as live_check,
                patch.object(manager, "_load_package", side_effect=[package, narrative]),
                patch("app.store_project_run", return_value=project),
                patch("app.project_list_item", return_value={"id": "project-2", "title": "恢复后的月报"}),
                patch("app.store_latest_agent_run"),
            ):
                manager._run(run_id)

            finished = manager.get(run_id)
            self.assertEqual(finished["status"], "completed")
            messages = [event["message"] for event in finished["events"]]
            self.assertEqual(live_check.call_count, 0)
            self.assertFalse(finished["checkpoints"]["preflight"]["browser_required"])
            self.assertTrue(any("加载标准化月报数据包" in message for message in messages))

    def test_resume_does_not_mix_months_or_discard_completed_checkpoints(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            manager = self.make_manager(directory)
            with patch.object(manager, "_spawn"):
                created = manager.start({**self.payload(), "report_month": "2026-09"})
            run_id = created["run_id"]
            manager._save_checkpoint(run_id, "data_collect", {"snapshot_path": "checkpoint.json", "report_month": "2026-08"})
            manager._save_checkpoint(run_id, "narrative", {"path": "narrative.json"})
            with (
                patch.object(manager, "_run_async_step", return_value={"page_ready": True, "report_month": "2026-09"}) as live_check,
                patch.object(manager, "_load_package", return_value=ready_package()),
            ):
                manager._run(run_id)
            state = manager.get(run_id)
            self.assertEqual(state["status"], "input_required")
            self.assertIn("data_collect", state["completed_phases"])
            self.assertIn("narrative", state["completed_phases"])
            self.assertEqual(live_check.call_count, 1)

    def test_new_run_reuses_same_month_validated_package_without_card_collection(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            manager = self.make_manager(directory)
            with patch.object(manager, "_spawn"):
                created = manager.start(self.payload())
            package = ready_package()
            package_path = Path(directory).resolve() / "outputs/monthly-report-data/reused.json"
            package_path.parent.mkdir(parents=True)
            disk_package = dict(package)
            disk_package.pop("snapshot_path")
            package_path.write_text(json.dumps(disk_package), encoding="utf-8")
            package["snapshot_path"] = str(package_path)
            seen_phases: list[str] = []

            def run_step(_run_id, phase, _progress, _description, _factory, max_attempts=2, **kwargs):
                del max_attempts, kwargs
                seen_phases.append(phase)
                manager._update(_run_id, phase, "running", _description, _progress)
                if phase == "preflight":
                    return {
                        "page_ready": True,
                        "code": "data_source_package_reused",
                        "report_month": "2026-08",
                        "snapshot_path": "preflight-audit.json",
                        "data_package_path": package["snapshot_path"],
                        "snapshot_reused": True,
                    }
                if phase == "narrative":
                    return {"narrative": ready_narrative(_run_id), "mcp_plugins": {}, "tool_events": []}
                raise AssertionError(f"unexpected phase: {phase}")

            project = {"id": "project-reuse", "title": "复用数据包的月报", "created_at": "2026-10-07T18:00:00"}
            with (
                patch.object(manager, "_run_async_step", side_effect=run_step),
                patch("app.PROJECT_DIR", Path(directory).resolve()),
                patch.object(manager, "_load_package", wraps=manager._load_package) as load_package,
                patch("app.store_project_run", return_value=project),
                patch("app.project_list_item", return_value={"id": "project-reuse", "title": "复用数据包的月报"}),
                patch("app.store_latest_agent_run"),
            ):
                manager._run(created["run_id"])

            finished = manager.get(created["run_id"])
            self.assertEqual(finished["status"], "completed")
            self.assertNotIn("data_collect", seen_phases)
            load_package.assert_called_once_with(package["snapshot_path"])
            self.assertEqual(finished["checkpoints"]["data_collect"]["snapshot_path"], str(package_path))
            self.assertEqual(finished["result"]["skill"]["source_package"]["snapshot_path"], str(package_path))
            self.assertNotIn("snapshot_path", json.loads(package_path.read_text(encoding="utf-8")))
            self.assertTrue(finished["checkpoints"]["data_collect"]["snapshot_reused"])
            self.assertEqual(finished["checkpoints"]["data_collect"]["cards_reused"], 45)
            self.assertEqual(finished["checkpoints"]["data_collect"]["cards_collected"], 0)
            self.assertEqual(finished["result"]["tool_events"][0]["name"], "monthly_report_reuse_data_package")
            self.assertEqual(finished["report_month"], "2026-08")
            messages = [event["message"] for event in finished["events"]]
            self.assertTrue(any("跳过45张卡片重复读取" in message for message in messages))

    def test_narrative_rule_upgrade_never_recollects_validated_cards(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            manager = self.make_manager(directory)
            with patch.object(manager, "_spawn"):
                created = manager.start(self.payload())
            run_id = created["run_id"]
            manager._save_checkpoint(run_id, "data_collect", {"snapshot_path": "data.json", "report_month": "2026-08"})
            manager._save_checkpoint(run_id, "narrative", {"path": "narrative.json"})
            old_narrative = {**ready_narrative(run_id), "narrative_rule_version": "prior-rule"}
            phases = []
            def step(_run_id, phase, progress, description, factory, **kwargs):
                phases.append(phase)
                if phase == "preflight":
                    return {"page_ready": True, "report_month": "2026-08"}
                if phase == "narrative":
                    return {"narrative": ready_narrative(run_id), "mcp_plugins": {}, "tool_events": []}
                raise AssertionError("Rule changes must not recapture cards: " + phase)
            with patch.object(manager, "_run_async_step", side_effect=step), patch.object(manager, "_load_package", side_effect=[ready_package(), old_narrative]), patch("app.store_project_run", return_value={"id": "upgraded"}), patch("app.project_list_item", return_value={"id": "upgraded"}), patch("app.store_latest_agent_run"):
                manager._run(run_id)
            state = manager.get(run_id)
            self.assertEqual(state["status"], "completed")
            self.assertEqual(phases, ["narrative"])
            self.assertEqual(state["checkpoints"]["data_collect"]["snapshot_path"], "data.json")
            self.assertEqual(state["checkpoints"]["narrative"]["rule_version"], app.NARRATIVE_RULE_VERSION)

    def test_explicit_month_and_refresh_request_are_persisted(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            manager = self.make_manager(directory)
            with patch.object(manager, "_spawn"):
                state = manager.start({**self.payload(), "report_month": "2026-08", "force_refresh": True})
                self.assertEqual(state["payload"]["report_month"], "2026-08")
                self.assertTrue(state["payload"]["force_refresh"])
                with self.assertRaises(ValueError):
                    manager.start({**self.payload(), "report_month": "2026-13"})

    def test_failed_data_gate_keeps_diagnostics_and_never_announces_ppt_or_completion(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            manager = self.make_manager(directory)
            with patch.object(manager, "_spawn"):
                created = manager.start(self.payload())
            package = {**ready_package(), "generation_ready": False, "cards_usable": 30,
                       "code": "data_package_incomplete", "unusable_cards": ["P1.2-1"],
                       "card_validation": {"P1.2-1": {"latest_period": "2026-07", "message": "目标月份尚未发布"}}}
            phases = []
            def step(run_id, phase, progress, description, factory, **kwargs):
                phases.append(phase)
                if phase == "preflight":
                    return {"page_ready": True, "report_month": "2026-08"}
                if phase == "data_collect":
                    return package
                raise AssertionError(phase)
            with patch.object(manager, "_run_async_step", side_effect=step), patch("app.store_project_run", return_value={"id": "diagnostic"}), patch("app.project_list_item", return_value={"id": "diagnostic"}), patch("app.store_latest_agent_run"):
                manager._run(created["run_id"])
            state = manager.get(created["run_id"])
            self.assertEqual(state["status"], "input_required")
            self.assertEqual(state["phase"], "data_gate")
            self.assertTrue(state["recoverable"])
            self.assertNotIn("data_gate", state["completed_phases"])
            self.assertNotIn("narrative", phases)
            self.assertNotIn("result_prepare", [x["phase"] for x in state["events"]])
            self.assertNotIn("completed", [x["phase"] for x in state["events"]])
            self.assertIn("2026-07", state["result"]["answer"])
            self.assertIn("目标月份尚未发布", state["result"]["answer"])

    def test_unconfirmed_month_stops_before_collection(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            manager = self.make_manager(directory)
            with patch.object(manager, "_spawn"):
                created = manager.start(self.payload())
            with patch.object(manager, "_run_async_step", return_value={"page_ready": True, "report_month": ""}) as step:
                manager._run(created["run_id"])
            self.assertEqual(step.call_count, 1)
            self.assertEqual(manager.get(created["run_id"])["status"], "input_required")

    def test_collector_cannot_overwrite_locked_month(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            manager = self.make_manager(directory)
            with patch.object(manager, "_spawn"):
                created = manager.start(self.payload())
            package = {**ready_package(), "report_month": "2026-09"}
            def step(run_id, phase, progress, description, factory, **kwargs):
                if phase == "preflight":
                    return {"page_ready": True, "report_month": "2026-08"}
                if phase == "data_collect":
                    return package
                raise AssertionError(phase)
            with patch.object(manager, "_run_async_step", side_effect=step), patch("app.store_project_run", return_value={"id": "diagnostic"}), patch("app.project_list_item", return_value={"id": "diagnostic"}), patch("app.store_latest_agent_run"):
                manager._run(created["run_id"])
            state = manager.get(created["run_id"])
            self.assertEqual(state["report_month"], "2026-08")
            self.assertEqual(state["status"], "input_required")
            self.assertEqual(state["error"]["type"], "report_month_mismatch")

    def test_cancelled_job_can_resume_from_existing_run_id(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            manager = self.make_manager(directory)
            with patch.object(manager, "_spawn"):
                created = manager.start(self.payload())
                cancelled = manager.cancel(created["run_id"])
                self.assertEqual(cancelled["phase"], "cancel")
                manager._update(created["run_id"], "cancelled", "cancelled", "已取消", 15, recoverable=True)
                resumed = manager.resume(created["run_id"])
            self.assertEqual(resumed["phase"], "resume")
            self.assertEqual(resumed["status"], "running")
            self.assertTrue(resumed["recoverable"])

    def test_login_required_preflight_is_rechecked_after_resume(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            manager = self.make_manager(directory)
            with patch.object(manager, "_spawn"):
                created = manager.start(self.payload())
            run_id = created["run_id"]
            manager._save_checkpoint(
                run_id,
                "preflight",
                {"page_ready": False, "code": "data_source_login_required"},
                completed=False,
            )
            manager._update(run_id, "preflight", "input_required", "等待登录", 15, recoverable=True)
            with patch.object(manager, "_spawn"):
                resumed = manager.resume(run_id)
            self.assertNotIn("preflight", resumed["completed_phases"])
            self.assertEqual(resumed["phase"], "resume")

    def test_project_archive_is_idempotent_by_run_id(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            project_file = Path(directory) / "project-runs.json"
            result = app.build_passenger_monthly_run_result(ready_package(), "minimax")
            with patch("app.PROJECT_RUNS_FILE", project_file):
                first = app.store_project_run(
                    result,
                    "生成乘用车月报",
                    "passenger_car_monthly_report",
                    "minimax",
                    ["passenger_car_monthly_report"],
                    run_id="month-fixed-run",
                )
                second = app.store_project_run(
                    result,
                    "生成乘用车月报",
                    "passenger_car_monthly_report",
                    "minimax",
                    ["passenger_car_monthly_report"],
                    run_id="month-fixed-run",
                )
            self.assertEqual(first["id"], second["id"])
            self.assertEqual(len(json.loads(project_file.read_text(encoding="utf-8"))), 1)


if __name__ == "__main__":
    unittest.main()
