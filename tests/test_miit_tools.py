"""S4 单测：款型配置信息工具（硬参数映射 / 工具契约 / 导入列校验）。"""
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

from tools.miit_tools import MiitService, MiitSearchModelsTool, MiitGetModelDetailTool, build_miit_toolkit
from utils.benchmark_research_dag import domain

# skill 包目录名带连字符，无法作为 Python 包导入；按文件路径加载导入脚本。
_IMPORT_MIIT_PATH = Path(__file__).resolve().parents[1] / "skills" / "competitor-benchmarking" / "scripts" / "import_miit.py"
_spec = importlib.util.spec_from_file_location("import_miit", _IMPORT_MIIT_PATH)
import_miit = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(import_miit)


class HardParamTests(unittest.TestCase):
    def test_extract_hard_params_keeps_three_range_standards(self):
        rows = [
            {"pz_name": "CLTC纯电续航里程(km)", "pz_value": "605"},
            {"pz_name": "WLTC纯电续航里程(km)", "pz_value": "480"},
            {"pz_name": "整备质量(kg)", "pz_value": "1885"},
            {"pz_name": "百公里耗电量(kWh/100km)", "pz_value": "13.8"},
            {"pz_name": "电池能量(kWh)", "pz_value": "71.8"},
        ]
        params = MiitService.extract_hard_params(rows)
        self.assertEqual(params["cltc_range_km"], {"CLTC纯电续航里程(km)": "605"})
        self.assertEqual(params["wltc_range_km"], {"WLTC纯电续航里程(km)": "480"})
        self.assertEqual(params["_primary_range_km"], "605")
        self.assertEqual(params["curb_weight_kg"], {"整备质量(kg)": "1885"})
        self.assertEqual(params["energy_consumption_kwh_100km"], {"百公里耗电量(kWh/100km)": "13.8"})
        self.assertEqual(params["battery_energy_kwh"], {"电池能量(kWh)": "71.8"})

    def test_missing_hard_params_are_empty_not_fabricated(self):
        params = MiitService.extract_hard_params([{"pz_name": "电池类型", "pz_value": "磷酸铁锂"}])
        self.assertEqual(params["_primary_range_km"], "")
        self.assertEqual(params["battery_energy_kwh"], {})


class ToolContractTests(unittest.TestCase):
    def test_toolkit_names_and_domain(self):
        tools = build_miit_toolkit()
        names = {t.name for t in tools}
        self.assertEqual(names, {"miit_search_models", "miit_get_model_detail"})
        for t in tools:
            self.assertEqual(domain(t.name), "miit")
        search = next(t for t in tools if t.name == "miit_search_models")
        detail = next(t for t in tools if t.name == "miit_get_model_detail")
        self.assertIn("model", search.input_schema["properties"])
        self.assertIn("car_id", detail.input_schema["properties"])
        self.assertEqual(detail.input_schema["required"], ["car_id"])


class ImportContractTests(unittest.TestCase):
    def test_read_rows_rejects_missing_columns(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        p = Path(tmp.name) / "base.csv"
        p.write_text("model_name,type_name,car_id\n宋PLUS,SUV,1\n", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "缺少列"):
            import_miit._read_rows(str(p), import_miit.BASE_COLS)

    def test_read_rows_accepts_contract_columns(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        p = Path(tmp.name) / "base.csv"
        p.write_text("model_name,type_name,car_id,file_name,create_time\n宋PLUS,SUV,1,f.csv,2026-09-01\n", encoding="utf-8")
        rows = import_miit._read_rows(str(p), import_miit.BASE_COLS)
        self.assertEqual(rows[0]["car_id"], "1")


if __name__ == "__main__":
    unittest.main()
