from __future__ import annotations

import os
import unittest
from unittest.mock import patch

from utils.model_factory import build_model


class ModelProviderAvailabilityTest(unittest.TestCase):
    def test_disabled_provider_is_rejected_before_reading_api_key(self) -> None:
        config = {
            "active_provider": "zhipu",
            "providers": {
                "zhipu": {
                    "type": "openai_compatible",
                    "base_url": "https://open.bigmodel.cn/api/paas/v4/",
                    "model": "glm-5.3",
                    "api_key_env": "ZHIPU_API_KEY",
                    "enabled": False,
                    "availability_note": "Coding Plan 凭证不能由独立 AgentScope 脚本调用。",
                }
            },
        }

        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaisesRegex(RuntimeError, "Coding Plan"):
                build_model(config)


if __name__ == "__main__":
    unittest.main()
