"""Regression tests for complete package-aware Skill execution."""

from __future__ import annotations

import asyncio
import importlib.util
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from skill_runtime import SkillRegistry, SkillRunContext, build_skill_runtime_tools


PROJECT = Path(__file__).resolve().parents[1]


def _tool_text(chunk: object) -> str:
    content = getattr(chunk, "content")
    return getattr(content[0], "text")


class SkillRegistryTest(unittest.TestCase):
    def setUp(self) -> None:
        self.registry = SkillRegistry([PROJECT / "skills"])
        self.package = self.registry.get("macro-monthly-report")

    def test_complete_macro_package_is_discovered(self) -> None:
        self.assertEqual(self.package.name, "macro-monthly-report")
        self.assertEqual(self.package.artifact_template["kind"], "presentation")
        reference = self.package.resolve(self.package.artifact_template["reference"])
        self.assertTrue(reference.is_file())
        self.assertGreater(reference.stat().st_size, 1_000_000)
        resources = {item["path"] for item in self.package.resources()}
        self.assertIn("assets/reference.pptx", resources)
        self.assertIn("references/data-and-qa-rules.md", resources)
        self.assertIn("references/source-queries.json", resources)
        self.assertIn("scripts/generate_forecast_baseline.py", resources)
        self.assertIn("scripts/validate_forecast_baseline.py", resources)

    def test_runtime_prompt_describes_package_tools_not_prompt_simulation(self) -> None:
        prompt = self.package.runtime_prompt("test-run")
        self.assertIn("完整 Skill 包已只读挂载", prompt)
        self.assertIn("skill_package_inspect", prompt)
        self.assertIn("skill_validate_run", prompt)
        self.assertIn("presentation_powerpoint_validate", prompt)
        self.assertIn("default to **forecast mode**", prompt)


class SkillRunContextTest(unittest.TestCase):
    def setUp(self) -> None:
        self.package = SkillRegistry([PROJECT / "skills"]).get("macro-monthly-report")
        self.temp = TemporaryDirectory()
        self.context = SkillRunContext(self.package, Path(self.temp.name), run_id="test-run")

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_task_graph_and_checkpoint_are_persisted(self) -> None:
        self.context.set_plan(
            [
                {"id": "inspect", "title": "检查模板", "success_criteria": "读取结构", "depends_on": []},
                {"id": "deliver", "title": "交付", "success_criteria": "PPTX通过", "depends_on": ["inspect"]},
            ]
        )
        self.context.update_task("inspect", "completed", "33页模板已读取", ["skill:assets/reference.pptx"])
        state = self.context.load_state()
        self.assertEqual(state["plan"][0]["status"], "completed")
        self.assertTrue(self.context.checkpoints_path.is_file())

    def test_presentation_skill_requires_an_actual_pptx_deliverable(self) -> None:
        self.context.set_plan(
            [{"id": "inspect", "title": "检查模板", "success_criteria": "完成", "depends_on": []}]
        )
        self.context.update_task("inspect", "completed", "完成")
        validation = self.context.validate()
        self.assertEqual(validation["status"], "failed")
        self.assertIn(
            "presentation_deliverable",
            {item["id"] for item in validation["checks"] if not item["passed"]},
        )

    def test_runtime_tools_inspect_and_copy_real_template(self) -> None:
        tools = {tool.name: tool for tool in build_skill_runtime_tools(self.context)}
        self.assertIn("workspace_write_text", tools)
        self.assertIn("skill_run_script", tools)
        self.assertIn("presentation_powerpoint_validate", tools)
        package = json.loads(_tool_text(asyncio.run(tools["skill_package_inspect"].call())))
        self.assertEqual(package["artifact_template"]["reference"], "assets/reference.pptx")
        copied = json.loads(
            _tool_text(
                asyncio.run(
                    tools["skill_copy_asset"].call(
                        "assets/reference.pptx",
                        "macro-test.pptx",
                    )
                )
            )
        )
        inventory = json.loads(
            _tool_text(
                asyncio.run(
                    tools["presentation_inspect"].call(copied["path"], include_text=False)
                )
            )
        )
        self.assertEqual(inventory["slides"], 33)
        self.assertGreaterEqual(inventory["charts"], 30)

    def test_presentation_completion_requires_structural_validation(self) -> None:
        self.context.set_plan(
            [{"id": "deliver", "title": "交付", "success_criteria": "完成", "depends_on": []}]
        )
        self.context.update_task("deliver", "completed", "完成")
        target = self.context.copy_asset("assets/reference.pptx", "macro-test.pptx")
        self.context.register_artifact(target, "presentation")
        validation = self.context.validate()
        failed = {item["id"] for item in validation["checks"] if not item["passed"]}
        self.assertIn("pptx_structure", failed)
        self.assertIn("macro_business", failed)
        self.assertIn("powerpoint_render", failed)
        self.assertIn("macro_layout", failed)

    def test_package_script_executes_inside_the_run_workspace(self) -> None:
        with TemporaryDirectory() as package_root, TemporaryDirectory() as runtime_root:
            root = Path(package_root) / "script-skill"
            (root / "scripts").mkdir(parents=True)
            (root / "SKILL.md").write_text(
                "---\nname: script-skill\ndescription: test package scripts\n---\nRun the script.",
                encoding="utf-8",
            )
            (root / "scripts" / "probe.py").write_text(
                "import os\nprint(os.environ['SKILL_RUN_ROOT'])\n",
                encoding="utf-8",
            )
            package = SkillRegistry([Path(package_root)]).get("script-skill")
            context = SkillRunContext(package, Path(runtime_root), run_id="script-run")
            tools = {tool.name: tool for tool in build_skill_runtime_tools(context)}
            result = json.loads(
                _tool_text(asyncio.run(tools["skill_run_script"].call("scripts/probe.py")))
            )
            self.assertTrue(result["success"])
            self.assertIn("script-run", result["stdout"])


class SkillRuntimeMcpTest(unittest.TestCase):
    def test_standard_mcp_surface_exposes_the_same_runtime_capabilities(self) -> None:
        path = PROJECT / "mcp" / "skill_runtime_server.py"
        spec = importlib.util.spec_from_file_location("skill_runtime_server_test", path)
        module = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        spec.loader.exec_module(module)
        names = {tool.name for tool in asyncio.run(module.mcp.list_tools())}
        self.assertTrue(
            {
                "skill_activate",
                "skill_package_inspect",
                "skill_plan_tasks",
                "workspace_write_text",
                "skill_run_script",
                "forecast_series",
                "presentation_update_chart",
                "presentation_powerpoint_validate",
                "skill_validate_run",
            }.issubset(names)
        )


if __name__ == "__main__":
    unittest.main()
