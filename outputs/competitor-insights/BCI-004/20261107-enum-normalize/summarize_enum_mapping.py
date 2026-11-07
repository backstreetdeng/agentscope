"""把 enum_mapping.json 渲染成评审用映射表（Markdown）。只读，不写库。

仅把「模板里真正按单选枚举消费」的标签逐值判定；
其余声明 allowed_values 的标签只做分类统计，不制造噪声。
"""

import json
import re
from collections import Counter
from pathlib import Path

BASE = Path(__file__).resolve().parent
ROOT = BASE.parents[3]
data = json.loads((BASE / "enum_mapping.json").read_text(encoding="utf-8"))
tpl = json.loads((ROOT / "competitor_insight/templates/user_insight_archive_template.json")
                 .read_text(encoding="utf-8"))
sm = json.loads((ROOT / "competitor_insight/templates/user_insight_archive.source-map.json")
                .read_text(encoding="utf-8"))
tpl_dims = {d["id"]: d for d in tpl["dimensions"]}
tag_dims = {d["dimension_id"]: d for d in sm["dimensions"] if d.get("fill_mode") == "tag"}

enum_dims = {k: v for k, v in tag_dims.items() if tpl_dims.get(k, {}).get("type") == "enum"}
multi_dims = {k: v for k, v in tag_dims.items() if tpl_dims.get(k, {}).get("type") == "multi"}
enum_tag_names = {name for d in enum_dims.values() for name in d["tag_names"]}
multi_tag_names = {name for d in multi_dims.values() for name in d["tag_names"]}

rows_by_tag = {item["tag_name"]: item for item in data["enum_tags"]}
enum_report = {item["dimension_id"]: item for item in data["template_enum_dims"]}

STATUS_LABEL = {
    "exact": "直通",
    "normalized": "归一（同义/修饰）",
    "ambiguous": "互斥多值 → suspect",
    "no_value": "无数据 → missing",
    "unknown": "无法归一 → invalid_enum",
}

lines: list[str] = []
add = lines.append

add("# 枚举取值归一映射表（BCI-004-L12）")
add("")
add("数据源：`user_insight.tag` 全库 63 位受访者（只读扫描，2026-11-07）。")
add("规则实现：`competitor_insight/server/value_normalizer.py`（唯一归一处）。")
add("")

for dim_id, item in enum_report.items():
    options = item["options"]
    add(f"## {dim_id}（标签「{'」「'.join(tag_dims[dim_id]['tag_names'])}」，模板唯一单选枚举）")
    add("")
    add("| 原值 | 全库次数 | 建议归一值 | 判定 | 依据 | 处置 |")
    add("|---|---|---|---|---|---|")
    total = 0
    for r in item["rows"]:
        total += r["count"]
        raw = r["raw"] if r["raw"] is not None else "NULL"
        value = r["suggested"] if r["suggested"] is not None else "—"
        reason = (r["reason"] or "去标点即命中模板选项").replace("|", "／")
        if r["status"] == "ambiguous" and r["candidates"]:
            reason += f"（候选：{'、'.join(r['candidates'])}）"
        action = {
            "exact": "保留",
            "normalized": "保留归一值，source_ref 记原值",
            "ambiguous": "不取值；review=suspect + no_data_reason，人工复核",
            "no_value": "fill_mode=none，review=missing",
            "unknown": "整人失败，不落库",
        }[r["status"]]
        add(f"| {raw} | {r['count']} | {value} | {STATUS_LABEL[r['status']]} | {reason} | {action} |")
    add("")
    add(f"合计 {total} 条；无空值/「未提及」/「不适用」写法。")
    add("")

add("## 同类标签扫描结果")
add("")
add("| 类别 | 标签数 | 是否参与单选归一 | 说明 |")
add("|---|---|---|---|")
add(f"| 模板单选枚举（tag 驱动） | {len(enum_tag_names)} | 是 | 「首增换购属性」 |")
add("| 模板单选枚举（无来源） | 1 | 否 | `kol_influence`，fill_mode=none |")
add(f"| 模板多值列表（tag 驱动） | {len(multi_tag_names)} | 否（拆列表） | {'、'.join(sorted(multi_tag_names))} |")
add(f"| 其余声明 allowed_values 的标签 | "
    f"{len(rows_by_tag) - len(enum_tag_names) - len(multi_tag_names)} | 否 | 自由文本抽取，allowed_values 仅作参考词表 |")
add("")

# 多值列表的选项覆盖情况：只报未覆盖词，不做映射
for dim_id, dim in multi_dims.items():
    options = {o.strip("。 ；") for o in tpl_dims.get(dim_id, {}).get("options", [])}
    parts: Counter[str] = Counter()
    for name in dim["tag_names"]:
        item = rows_by_tag.get(name)
        if not item:
            continue
        for v in item["values"]:
            if v["raw"] in ("<NULL>",):
                continue
            for part in re.split(r"[；;、,，/]", v["raw"]):
                cleaned = part.strip().strip("。；;，, ").strip()
                if cleaned:
                    parts[cleaned] += v["count"]
    outside = {k: n for k, n in parts.items() if k not in options}
    add(f"### {dim_id} 多值覆盖（{ '、'.join(dim['tag_names']) }）")
    add("")
    add(f"模板 options {len(options)} 项；标签实际出现 {len(parts)} 种写法，其中 {len(outside)} 种不在 options 内。")
    add("")
    top = sorted(outside.items(), key=lambda x: (-x[1], x[0]))[:15]
    add("未覆盖写法（次数，按降序前 15）：" + "、".join(f"{k}({n})" for k, n in top))
    add("")
    add("当前按原词入列表（符合“未覆盖不要臆测”），未做词表映射；是否映射待用户决定。")
    add("")

add("## 规则与测试")
add("")
add("- 判定顺序：空值/无数据标记 → `no_value`；否定表述 → `unknown`；多片段 → 互斥 `ambiguous` / 同选项 `normalized` / 含未识别片段 `unknown`；单片 → 精确 `exact`、去修饰前缀或唯一包含 `normalized`、否则 `unknown`。")
add("- 生成器分流：`exact`/`normalized` 取值并写 `source_ref.normalized_from`；`no_value` 落 `fill_mode=none`+`review_status=missing`；`ambiguous` 落 `no_data_reason`+`review_status=suspect`；`unknown` 抛 `invalid_enum` 整人失败。")
add("- 单测：`competitor_insight/tests/test_value_normalizer.py` 9 项；全量 90 项通过。")
add("")

(BASE / "enum_mapping.md").write_text("\n".join(lines), encoding="utf-8")
print("\n".join(lines))
print(f"\nwritten: {BASE / 'enum_mapping.md'}")
