"""BCI-004 · 档案维度名按用户车系参数化（用户 2026-11-09 拍板）。

- 模板里的 `{brand}` / `{vehicle}` 占位符在渲染、导出、生成提示词时替换：
  `{brand}` = 用户所购品牌（如 理想），`{vehicle}` = 车系全名（如 理想i8）；
- 转化语义维度（转化机会/风险）保留「本品（埃安RT）」措辞，不参与替换；
- 品牌映射仅覆盖当前深访库的 22 个车系，新增车系须同步补表，缺省回退为车系全名。
"""

from __future__ import annotations

import re

# vehicle_model → 品牌（覆盖 user_insight.interview 全部 22 个取值，2026-11-09 实测）
BRAND_BY_MODEL: dict[str, str] = {
    "理想i8": "理想",
    "领克900": "领克",
    "极氪007GT": "极氪",
    "银河星耀8": "银河",
    "银河A7": "银河",
    "零跑B10": "零跑",
    "小米YU7": "小米",
    "日产N7": "日产",
    "海狮05 EV": "比亚迪",
    "海豹05": "比亚迪",
    "唐L": "比亚迪",
    "夏": "比亚迪",
    "比亚迪夏": "比亚迪",
    "铂智3X": "铂智",
    "钛3": "方程豹",
    "乐道L90": "乐道",
    "启源Q07": "启源",
    "奇瑞iCAR V23": "iCAR",
    "iCAR V23": "iCAR",
    "腾势N9": "腾势",
    "问界M8": "问界",
    "智界R7": "智界",
}

_PLACEHOLDER = re.compile(r"\{(brand|vehicle)\}")


def brand_of(vehicle_model: str | None) -> str:
    value = (vehicle_model or "").strip()
    if not value:
        return ""
    mapped = BRAND_BY_MODEL.get(value)
    if mapped:
        return mapped
    # 回退：车系名末尾的型号段通常是字母数字（i8/900/B10/007GT…），剥掉后即品牌
    stripped = re.sub(r"[A-Za-z0-9\- ]+$", "", value).strip()
    return stripped or value


def naming_for(vehicle_model: str | None) -> dict[str, str]:
    value = (vehicle_model or "").strip()
    return {"brand": brand_of(value), "vehicle": value}


def resolve_name(name: str | None, vehicle_model: str | None) -> str:
    """把模板维度名/组名/描述里的占位符替换为用户实际品牌与车系。"""
    if not name:
        return name or ""
    naming = naming_for(vehicle_model)
    return _PLACEHOLDER.sub(
        lambda m: naming[m.group(1)] if naming[m.group(1)] else m.group(0), name
    )


def neutral_name(name: str | None) -> str:
    """多人合并导出时无法按人替换，退化为中性别名；模板可用 name_generic 覆盖。"""
    if not name:
        return name or ""
    return _PLACEHOLDER.sub(lambda m: "自有" if m.group(1) == "brand" else "该车型", name)
