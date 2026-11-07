"""补充核对：RE010 类 ID 是否存在、`实际增购。`标签归属、试点名单覆盖。只读。"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT))

from competitor_insight.server import db  # noqa: E402

conn = db.connect()
with conn.cursor() as cur:
    cur.execute(
        "select interview_id, respondent_code from user_insight.interview"
        " where interview_id like %s or respondent_code like %s",
        ("%E010%", "%E010%"),
    )
    print("E010_LIKE", cur.fetchall())
    cur.execute(
        "select interview_id, tag_value, trust_status from user_insight.tag"
        " where tag_name = '首增换购属性' and tag_value not in ('首购。','换购。','增购。')"
    )
    print("NON_STANDARD", cur.fetchall())
    cur.execute("select interview_id from bci.archive order by interview_id")
    print("ARCHIVED", [r[0] for r in cur.fetchall()])
    cur.execute(
        "select interview_id, purchase_type from user_insight.interview"
        " where purchase_type is not null and purchase_type <> ''"
        " order by 1 limit 70"
    )
    rows = cur.fetchall()
    print("PURCHASE_TYPE_DIST", len(rows), rows[:10])
conn.close()
