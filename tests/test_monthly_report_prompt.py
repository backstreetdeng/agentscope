"""月报任务与通用市场战略任务的提示词边界测试。"""

from __future__ import annotations

import unittest

from agents.market_strategy_agent import MARKET_MONTHLY_REPORT_PROMPT


class MonthlyReportPromptTest(unittest.TestCase):
    def test_monthly_report_prompt_requires_complete_monthly_structure(self) -> None:
        self.assertIn("2.3、2.4、2.5", MARKET_MONTHLY_REPORT_PROMPT)
        self.assertIn("2,100-2,700", MARKET_MONTHLY_REPORT_PROMPT)
        self.assertNotIn("1200-1600", MARKET_MONTHLY_REPORT_PROMPT)
        self.assertIn("数据来源与数据缺口", MARKET_MONTHLY_REPORT_PROMPT)
        self.assertIn("待核验假设", MARKET_MONTHLY_REPORT_PROMPT)


if __name__ == "__main__":
    unittest.main()
