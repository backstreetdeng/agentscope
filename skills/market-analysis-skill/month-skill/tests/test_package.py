"""Offline package-level regression tests."""

from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def load_script(name: str):
    path = ROOT / "scripts" / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


class PackageTest(unittest.TestCase):
    def test_package_validator_passes(self) -> None:
        validator = load_script("validate_package")
        result = validator.validate()
        self.assertTrue(result["ok"], result["errors"])

    def test_installer_is_dry_run_by_default(self) -> None:
        installer = load_script("install_into_project")
        with tempfile.TemporaryDirectory() as temp_dir:
            target = Path(temp_dir)
            files = installer.iter_install_files(target)
            self.assertGreater(len(files), 10)
            self.assertFalse(any(destination.exists() for _, destination in files))

    def test_fresh_install_and_runtime_smoke(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            target = Path(temp_dir)
            (target / "main.py").write_text("# host project marker\n", encoding="utf-8")
            installer = ROOT / "scripts" / "install_into_project.py"
            installed = subprocess.run(
                [sys.executable, str(installer), "--target", str(target), "--apply"],
                check=False,
                capture_output=True,
                text=True,
                encoding="utf-8",
            )
            self.assertEqual(installed.returncode, 0, installed.stdout + installed.stderr)
            payload = json.loads(installed.stdout)
            self.assertTrue(payload["ok"])
            self.assertTrue(
                (target / "skills" / "market_analysis_skill" / "runtime.py").is_file()
            )
            self.assertTrue(
                (
                    target
                    / "skills"
                    / "market_analysis_skill"
                    / "profiles"
                    / "passenger_vehicle_monthly"
                    / "assets"
                    / "monthly_report_template.pptx"
                ).is_file()
            )

            environment = os.environ.copy()
            environment["PYTHONPATH"] = str(target)
            smoke = subprocess.run(
                [
                    sys.executable,
                    "-c",
                    (
                        "from skills.market_analysis_skill import MarketAnalysisSkill; "
                        "c=MarketAnalysisSkill().prepare('请生成月报','market_monthly_report'); "
                        "print(c.selected_sheet, len(c.top_model_records), c.input_gate())"
                    ),
                ],
                cwd=target,
                env=environment,
                check=False,
                capture_output=True,
                text=True,
                encoding="utf-8",
            )
            self.assertEqual(smoke.returncode, 0, smoke.stdout + smoke.stderr)
            self.assertIn("6月 45", smoke.stdout)

            report_text = """# 2026年6月中国乘用车市场分析报告
## 2.1 车型类别
### 结构分化延续，主力类别仍需核验产品驱动
6月，各车型类别走势继续分化，代表车型变化与产品周期原因需结合证据核验。
## 2.2 车型级别
### 主流级别竞争加剧，结构变化仍需持续观察
6月，各级别市场表现分化，新增供给和同期基数是后续核验重点。
## 2.3 轿车级别分析
### 轿车内部结构分化，代表车型变化反映产品周期差异
6月，轿车市场内部级别表现分化，具体车型原因需结合事件资料核验。
## 2.4 SUV级别分析
### SUV主流级别竞争持续，新老产品承接决定后续走势
6月，SUV市场仍由主力车型竞争和产品切换共同影响。
## 2.5 MPV级别分析
### MPV核心车型波动加大，换新窗口仍是主要观察点
6月，MPV市场受核心车型产品周期影响，后续需跟踪换代节奏。
"""
            output_path = target / "smoke_monthly_report.pptx"
            dataset_path = (
                target
                / "skills"
                / "market_analysis_skill"
                / "profiles"
                / "passenger_vehicle_monthly"
                / "assets"
                / "demo_monthly_data.xlsx"
            )
            render_code = (
                "from pathlib import Path; "
                "from utils.monthly_report_pptx import build_monthly_report_pptx; "
                f"r=build_monthly_report_pptx({report_text!r}, Path({str(output_path)!r}), "
                f"Path({str(dataset_path)!r}), sheet_name='6月'); "
                "print(r['slides_count'], r['period'])"
            )
            rendered = subprocess.run(
                [sys.executable, "-c", render_code],
                cwd=target,
                env=environment,
                check=False,
                capture_output=True,
                text=True,
                encoding="utf-8",
            )
            self.assertEqual(rendered.returncode, 0, rendered.stdout + rendered.stderr)
            self.assertIn("5 2026年6月", rendered.stdout)
            self.assertTrue(output_path.is_file())
            self.assertGreater(output_path.stat().st_size, 100_000)

            regression = subprocess.run(
                [sys.executable, "-m", "unittest", "discover", "-s", "tests", "-v"],
                cwd=target,
                env=environment,
                check=False,
                capture_output=True,
                text=True,
                encoding="utf-8",
            )
            self.assertEqual(regression.returncode, 0, regression.stdout + regression.stderr)

    def test_profile_has_five_pages(self) -> None:
        import yaml

        specs = yaml.safe_load(
            (ROOT / "profiles" / "passenger_vehicle_monthly" / "page_specs.yaml").read_text(encoding="utf-8")
        )
        self.assertEqual(len(specs["pages"]), 5)
        self.assertEqual([page["template_slide_index"] for page in specs["pages"]], list(range(5)))


if __name__ == "__main__":
    unittest.main()
