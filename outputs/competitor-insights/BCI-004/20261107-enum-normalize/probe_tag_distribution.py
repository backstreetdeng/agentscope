"""枚举类标签取值分布：按 source-map 找出 tag 驱动的维度，输出全库取值与次数。只读。"""

import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT))

from competitor_insight.server import db  # noqa: E402

SM = json.loads((ROOT / "competitor_insight/templates/user_insight_archive.source-map.json")
                .read_text(encoding="utf-8"))
TPL = json.loads((ROOT / "competitor_insight/templates/user_insight_archive_template.json")
                 .read_text(encoding="utf-8"))
dims = {d["id"]: d for d in TPL["dimensions"]}

tag_dims = []
for d in SM["dimensions"]:
    if d.get("fill_mode") != "tag":
        continue
    meta = dims.get(d["dimension_id"], {})
    tag_dims.append({
        "dimension_id": d["dimension_id"],
        "dtype": meta.get("type"),
        "options": meta.get("options"),
        "tag_names": d.get("tag_names") or [],
    })

print("TAG_DIMS", len(tag_dims))
print(json.dumps(tag_dims, ensure_ascii=False, indent=1))

conn = db.connect()
with conn.cursor() as cur:
    for item in tag_dims:
        for tag_name in item["tag_names"]:
            cur.execute(
                "select coalesce(tag_value, '<null>'), count(*) from user_insight.tag"
                " where tag_name = %s group by 1 order by 2 desc, 1",
                (tag_name,),
            )
            rows = cur.fetchall()
            allowed = item["options"]
            print("\n###", item["dimension_id"], "|", item["dtype"], "|", tag_name,
                  "| rows =", sum(r[1] for r in rows), "| allowed =", allowed)
            for value, n in rows:
                flag = ""
                if allowed:
                    if value not in allowed:
                        flag = " <-- 非标准"
                print(f"  {value!r}\t{n}{flag}")
conn.close()
