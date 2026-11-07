"""导出 info_channels 全库写法与次数（只读）。

按 source-map 中 info_channels 依赖的标签（汽车触媒偏好 / APP偏好），
把每条标签值按分隔符拆成渠道词，统计出现次数（同一条标签内重复只计一次）。
输出 channel_distribution.json，供归并表逐条核对。
"""

import json
import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT))

from competitor_insight.server import db  # noqa: E402
from competitor_insight.server.evidence_gate import normalize_value  # noqa: E402

OUT = Path(__file__).resolve().parent / "channel_distribution.json"
SPLIT = re.compile(r"[；;、,，/]")

sm = json.loads((ROOT / "competitor_insight/templates/user_insight_archive.source-map.json")
                .read_text(encoding="utf-8"))
dim = next(d for d in sm["dimensions"] if d["dimension_id"] == "info_channels")
tag_names = list(dim["tag_names"])

counter: Counter[str] = Counter()
null_values = 0
total_records = 0
conn = db.connect()
with conn.cursor() as cur:
    for name in tag_names:
        cur.execute(
            "select tag_value from user_insight.tag where tag_name = %s and trust_status = '可信'",
            (name,),
        )
        for (raw,) in cur.fetchall():
            total_records += 1
            if raw is None or not normalize_value(raw):
                null_values += 1
                continue
            parts = []
            for part in SPLIT.split(raw):
                cleaned = normalize_value(part)
                if cleaned and cleaned not in parts:
                    parts.append(cleaned)
            counter.update(parts)
conn.close()

report = {
    "source": "user_insight.tag（tag_name in %s，trust_status=可信），快照 2026-11-07" % tag_names,
    "total_tag_records": total_records,
    "null_or_empty": null_values,
    "distinct": len(counter),
    "entries": [{"raw": k, "count": v} for k, v in sorted(counter.items(), key=lambda x: (-x[1], x[0]))],
}
OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

print(f"records={total_records} null={null_values} distinct={len(counter)}")
for i, item in enumerate(report["entries"], 1):
    print(f"{i:>2}. {item['raw']}\t{item['count']}")
print(f"written: {OUT}")
