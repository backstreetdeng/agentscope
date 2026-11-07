"""全库枚举标签取值分布：找出所有非标准写法。只读。"""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT))

from competitor_insight.server import db  # noqa: E402

conn = db.connect()
with conn.cursor() as cur:
    cur.execute(
        "select tag_name, count(*) as n, count(distinct tag_value) as distinct_n,"
        " max(allowed_values::text) as allowed_sample"
        " from user_insight.tag"
        " where allowed_values is not null and allowed_values::text not in ('null', '[]', '\"\"')"
        " group by 1 order by 1"
    )
    rows = cur.fetchall()
    print("ENUM_TAGS", len(rows))
    for name, n, distinct_n, allowed in rows:
        print(json.dumps({"tag_name": name, "rows": n, "distinct": distinct_n,
                          "allowed": allowed}, ensure_ascii=False))
conn.close()
