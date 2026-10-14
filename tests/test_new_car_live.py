import json
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from integrations.new_car_live import decode, map_model, map_planned, read_pages, summarize


def result(data, error=False):
    return SimpleNamespace(isError=error, content=[SimpleNamespace(type="text", text=json.dumps(data))])


class NewCarLiveTests(unittest.IsolatedAsyncioTestCase):
    def test_mapping_keeps_id_and_all_base_fields(self):
        row = map_model({"id": 76796, "launch_year": 2026, "launch_month": 6,
                         "vehicle_type": "SUV", "enterprise": "奇瑞汽车", "import_batch": "202609"})
        self.assertEqual((row["id"], row["month"], row["cat"], row["corp"]), (76796, 6, "SUV", "奇瑞汽车"))
        self.assertEqual(len(row), 15)
        self.assertIsNone(row['style_name'])
        self.assertEqual(map_model({'style_name':'2026款 Max'})['style_name'],'2026款 Max')

    def test_summary_is_month_based_and_brand_model_unique(self):
        rows = [{"year": 2026, "month": 8, "brand": "A", "model": "同名"},
                {"year": 2026, "month": 9, "brand": "A", "model": "同名"},
                {"year": 2026, "month": 9, "brand": "B", "model": "同名"}]
        data = summarize(rows, {"planned_count": 312})
        self.assertEqual((data["spec_total"], data["series_total"], data["recent_total"]), (3, 2, 2))
        self.assertEqual(data["latest_month"], "2026-09")
        self.assertIsNone(data["last_successful_import"])

    def test_empty_dataset_is_valid(self):
        self.assertEqual(summarize([], {})["spec_total"], 0)

    def test_planned_mapping(self):
        self.assertEqual(map_planned({"market_status": "规划", "launch_year": "2027"})["status"], "规划")

    def test_errors_not_silently_accepted(self):
        for data, error in [({"success": False}, False), ({"success": True}, True)]:
            with self.assertRaises(ValueError):
                decode(result(data, error))

    async def test_pages_and_unique_ids(self):
        session = SimpleNamespace(call_tool=AsyncMock(side_effect=[
            result({"success": True, "total_count": 2, "items": [{"id": 1}], "has_more": True, "next_offset": 1}),
            result({"success": True, "total_count": 2, "items": [{"id": 2}], "has_more": False})]))
        self.assertEqual(len(await read_pages(session, "search", 2)), 2)
        self.assertEqual(session.call_tool.call_args_list[1].args[1]["params"]["offset"], 1)

    async def test_duplicate_or_changed_count_rejected(self):
        for page in [
            {"success": True, "total_count": 2, "items": [{"id": 1}, {"id": 1}]},
            {"success": True, "total_count": 3, "items": [{"id": 1}]},
            {"success": True, "total_count": 2, "items": [], "has_more": True, "next_offset": 0},
        ]:
            session = SimpleNamespace(call_tool=AsyncMock(return_value=result(page)))
            with self.assertRaises(ValueError):
                await read_pages(session, "search", 2)


if __name__ == "__main__":
    unittest.main()
