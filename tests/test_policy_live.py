import unittest
from types import SimpleNamespace

from integrations.policy_live import decode_result, summarize


class PolicyLiveTests(unittest.TestCase):
    def test_summary_uses_records_not_snapshot(self):
        rows = [{"记录编号": "a", "省份": "吉林", "城市": "白山", "政策名称": "消费券",
                 "监测日期/发布日期": "2026-09-14"},
                {"记录编号": "b", "省份": "吉林", "城市": "白山", "政策名称": "置换补助"},
                {"记录编号": "empty", "政策名称": ""}]
        result = summarize({"record_count": 9999}, rows)
        self.assertEqual(result["total"], 3)
        self.assertEqual(result["provinceCount"], 1)
        self.assertEqual(result["cityCount"], 1)
        self.assertEqual(result["blankCount"], 1)
        self.assertEqual(result["lastSuccessfulImport"], "未提供")
        self.assertEqual(result["latestCollectionDate"], "2026-09-14")
        self.assertEqual(result["latest"][0]["记录编号"], "a")
        self.assertEqual(next(t["count"] for t in result["topics"] if t["label"] == "消费券"), 1)

    def test_empty_is_not_error(self):
        result = summarize({}, [])
        self.assertEqual(result["total"], 0)
        self.assertEqual(result["latest"], [])

    def test_tool_error_is_not_silent_fallback(self):
        with self.assertRaises(ValueError):
            decode_result(SimpleNamespace(isError=True, content=[]))
        with self.assertRaises(ValueError):
            decode_result(SimpleNamespace(isError=False, content=[SimpleNamespace(type="text", text='{"success":false}')]))


if __name__ == "__main__":
    unittest.main()
