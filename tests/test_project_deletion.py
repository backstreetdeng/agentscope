from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import app


PROJECT_ROOT = Path(__file__).resolve().parents[1]


class ProjectDeletionTest(unittest.TestCase):
    def test_project_page_exposes_batch_delete_selection_controls(self) -> None:
        html = (PROJECT_ROOT / "home.html").read_text(encoding="utf-8")
        script = (PROJECT_ROOT / "assets" / "home.js").read_text(encoding="utf-8")
        self.assertIn("id='projectBatchDelete'", html)
        self.assertIn("id='projectSelectAll'", html)
        self.assertIn('data-select-project=', script)
        self.assertIn("async function deleteSelectedProjects()", script)
        self.assertIn("item.status !== '执行中'", script)

    def test_project_page_does_not_merge_legacy_demo_records(self) -> None:
        script = (PROJECT_ROOT / "assets" / "home.js").read_text(encoding="utf-8")
        self.assertNotIn("function legacyItems()", script)
        self.assertNotIn("saved.concat(legacyItems())", script)
        self.assertIn("state.items = saved;", script)

    def test_delete_project_removes_only_requested_record(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            ledger = Path(directory) / "project_runs.json"
            ledger.write_text(
                json.dumps([
                    {"id": "proj-delete", "status": "已失败", "title": "无效任务"},
                    {"id": "proj-keep", "status": "已完成", "title": "保留任务"},
                ], ensure_ascii=False),
                encoding="utf-8",
            )
            with patch.object(app, "PROJECT_RUNS_FILE", ledger):
                deleted = app.delete_project_run("proj-delete")
            self.assertEqual(deleted["id"], "proj-delete")
            remaining = json.loads(ledger.read_text(encoding="utf-8"))
            self.assertEqual([item["id"] for item in remaining], ["proj-keep"])

    def test_running_project_cannot_be_deleted(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            ledger = Path(directory) / "project_runs.json"
            ledger.write_text(
                json.dumps([{"id": "proj-running", "status": "执行中"}], ensure_ascii=False),
                encoding="utf-8",
            )
            with patch.object(app, "PROJECT_RUNS_FILE", ledger):
                with self.assertRaisesRegex(ValueError, "任务仍在执行"):
                    app.delete_project_run("proj-running")
            remaining = json.loads(ledger.read_text(encoding="utf-8"))
            self.assertEqual(remaining[0]["id"], "proj-running")


if __name__ == "__main__":
    unittest.main()
