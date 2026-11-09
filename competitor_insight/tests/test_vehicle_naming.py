"""vehicle_naming 单测：品牌映射、占位符替换、多人中性名。"""

from __future__ import annotations

import unittest

from competitor_insight.server.vehicle_naming import (
    brand_of,
    naming_for,
    neutral_name,
    resolve_name,
)


class VehicleNamingTest(unittest.TestCase):
    def test_brand_mapping_covers_known_models(self) -> None:
        self.assertEqual(brand_of("理想i8"), "理想")
        self.assertEqual(brand_of("领克900"), "领克")
        self.assertEqual(brand_of("唐L"), "比亚迪")
        self.assertEqual(brand_of("比亚迪夏"), "比亚迪")
        self.assertEqual(brand_of("奇瑞iCAR V23"), "iCAR")
        self.assertEqual(brand_of("钛3"), "方程豹")

    def test_brand_fallback_strips_model_suffix(self) -> None:
        self.assertEqual(brand_of("智界R7"), "智界")
        self.assertEqual(brand_of("未知X9"), "未知")

    def test_resolve_name_brand_and_vehicle(self) -> None:
        self.assertEqual(
            resolve_name("对{brand}品牌的印象", "理想i8"),
            "对理想品牌的印象",
        )
        self.assertEqual(
            resolve_name("对{vehicle}的认知与态度", "理想i8"),
            "对理想i8的认知与态度",
        )
        self.assertEqual(
            resolve_name("作为{brand}老车主 为什么继续再买{brand}的车", "领克900"),
            "作为领克老车主 为什么继续再买领克的车",
        )

    def test_resolve_name_without_vehicle_keeps_placeholder(self) -> None:
        self.assertEqual(resolve_name("对{brand}品牌", None), "对{brand}品牌")

    def test_naming_for(self) -> None:
        self.assertEqual(naming_for("零跑B10"), {"brand": "零跑", "vehicle": "零跑B10"})
        self.assertEqual(naming_for(""), {"brand": "", "vehicle": ""})

    def test_neutral_name(self) -> None:
        self.assertEqual(neutral_name("对{brand}品牌的印象"), "对自有品牌的印象")
        self.assertEqual(neutral_name("{vehicle}吸引力排序"), "该车型吸引力排序")


if __name__ == "__main__":
    unittest.main()
