"""查看 user_insight.tag / evidence 列名，便于后续精确取数。只读。"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT))

from competitor_insight.server import db  # noqa: E402

conn = db.connect()
with conn.cursor() as cur:
    for table in ("tag", "tag_evidence", "evidence", "answer"):
        cur.execute(
            "select column_name, data_type from information_schema.columns"
            " where table_schema = 'user_insight' and table_name = %s"
            " order by ordinal_position",
            (table,),
        )
        print(table, "=", [r[0] for r in cur.fetchall()])
conn.close()
