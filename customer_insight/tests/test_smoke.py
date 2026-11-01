"""T1 开发期 Harness 冒烟测试。

仅验证包骨架与测试入口已接线；不涉及任何业务能力，不代表真实业务验收。
"""

import unittest

import customer_insight


class HarnessSmokeTests(unittest.TestCase):
    def test_package_importable(self):
        self.assertTrue(hasattr(customer_insight, "__version__"))

    def test_version_is_set(self):
        self.assertIsInstance(customer_insight.__version__, str)
        self.assertTrue(customer_insight.__version__)


if __name__ == "__main__":
    unittest.main()
