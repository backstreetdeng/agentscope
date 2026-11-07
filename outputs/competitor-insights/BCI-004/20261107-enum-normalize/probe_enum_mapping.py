"""全库枚举类标签取值分布 + 归一映射表。只读，不写库。

产出：
1. 所有带 allowed_values 的标签，按 tag_name 汇总全库取值与次数；
2. 对档案模板里的枚举维（source-map fill_mode=tag & type=enum），逐值跑 value_normalizer，
   给出建议归一值与依据；
3. 结果写 enum_mapping.json，同时打印可读表。

用法：../Scripts/python.exe -B outputs/competitor-insights/BCI-004/20261107-enum-normalize/probe_enum_mapping.py
"""

import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT))

from competitor_insight.server import db  # noqa: E402
from competitor_insight.server.value_normalizer import resolve_enum  # noqa: E402

OUT = Path(__file__).resolve().parent / "enum_mapping.json"
TPL = json.loads((ROOT / "competitor_insight/templates/user_insight_archive_template.json")
                 .read_text(encoding="utf-8"))
SM = json.loads((ROOT / "competitor_insight/templates/user_insight_archive.source-map.json")
                .read_text(encoding="utf-8"))
tpl_dims = {d["id"]: d for d in TPL["dimensions"]}

tag_dims = [
    {
        "dimension_id": d["dimension_id"],
        "dtype": tpl_dims.get(d["dimension_id"], {}).get("type"),
        "options": tpl_dims.get(d["dimension_id"], {}).get("options"),
        "tag_names": d.get("tag_names") or [],
    }
    for d in SM["dimensions"]
    if d.get("fill_mode") == "tag"
]

conn = db.connect()
report: dict = {"enum_tags": [], "template_enum_dims": []}
with conn.cursor() as cur:
    # 1) 全库所有声明了 allowed_values 的标签
    cur.execute(
        """
        select tag_name, allowed_values, count(*) as total
        from user_insight.tag
        where allowed_values is not null
        group by 1, 2
        order by total desc, tag_name
        """
    )
    enum_tags = cur.fetchall()
    detailed = {
        name
        for item in tag_dims
        if item["dtype"] in ("enum", "multi")
        for name in item["tag_names"]
    }
    for tag_name, allowed, total in enum_tags:
        if tag_name not in detailed:
            # 自由文本标签只记规模，避免把 558KB 原值灌进证据文件
            cur.execute(
                "select count(distinct tag_value) from user_insight.tag where tag_name = %s",
                (tag_name,),
            )
            report["enum_tags"].append(
                {
                    "tag_name": tag_name,
                    "allowed_values": allowed,
                    "total": total,
                    "distinct_values": cur.fetchone()[0],
                    "values": None,
                }
            )
            continue
        cur.execute(
            "select coalesce(tag_value, '<NULL>'), count(*) from user_insight.tag"
            " where tag_name = %s group by 1 order by 2 desc, 1",
            (tag_name,),
        )
        values = [{"raw": v, "count": n} for v, n in cur.fetchall()]
        report["enum_tags"].append(
            {"tag_name": tag_name, "allowed_values": allowed, "total": total, "values": values}
        )

    # 2) 模板枚举维逐值归一（只读判定，不落库）
    for item in tag_dims:
        if item["dtype"] != "enum":
            continue
        options = item["options"] or []
        dim_rows = []
        for tag_name in item["tag_names"]:
            cur.execute(
                "select coalesce(tag_value, '<NULL>'), count(*) from user_insight.tag"
                " where tag_name = %s group by 1 order by 2 desc, 1",
                (tag_name,),
            )
            for raw, n in cur.fetchall():
                actual = None if raw == "<NULL>" else raw
                res = resolve_enum(actual or "", options)
                dim_rows.append(
                    {
                        "tag_name": tag_name,
                        "raw": actual,
                        "count": n,
                        "suggested": res.value,
                        "status": res.status,
                        "reason": res.reason,
                        "candidates": res.candidates,
                    }
                )
        report["template_enum_dims"].append(
            {"dimension_id": item["dimension_id"], "options": options, "rows": dim_rows}
        )
conn.close()

OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

print("=== 1. 全库声明了 allowed_values 的标签 ===")
for item in report["enum_tags"]:
    if item["values"] is None:
        print(f"\n## {item['tag_name']} | 全库 {item['total']} 条 | "
              f"{item['distinct_values']} 种写法（自由文本，不参与单选归一）")
        continue
    print(f"\n## {item['tag_name']} | 全库 {item['total']} 条 | allowed={item['allowed_values']}")
    for v in item["values"]:
        print(f"   {v['raw']!r}\t{v['count']}")

print("\n=== 2. 模板枚举维归一判定 ===")
for dim in report["template_enum_dims"]:
    print(f"\n## {dim['dimension_id']} | options={dim['options']}")
    for row in dim["rows"]:
        tail = f" 依据：{row['reason']}" if row["reason"] else ""
        cand = f" candidates={row['candidates']}" if row["candidates"] else ""
        print(
            f"   {row['raw']!r}\t{row['count']}\t-> {row['suggested']!r}\t"
            f"[{row['status']}]{cand}{tail}"
        )

print(f"\nwritten: {OUT}")
