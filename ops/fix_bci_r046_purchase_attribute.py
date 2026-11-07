"""BCI-004：R046「购车属性（首增换购）」互斥值核实后的可追溯修正。可重复执行。

来源链路：bci.archive_field.purchase_attribute ← user_insight.tag TAG-377357cc173d61c8ce47
（标签「首增换购属性」，取值「换购；增购。」，mapped_question_ids=[1]，可信）。
原文：Q1 答案 + tag_evidence TEI-91315ed80cf5faca5d12（3055.8–3089.4）明确旧车由妻子继续使用、
购入时未卖，家庭口径为增购；interview.purchase_type=增购 交叉一致。

行为：只在当前仍为原 suspect 状态时写入；保留原值与原原因到 source_ref.correction；
按模板 required 重算该档案的 coverage_required / status。不打印任何凭据。

用法：../Scripts/python.exe -B ops/fix_bci_r046_purchase_attribute.py
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from psycopg2.extras import Json

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from competitor_insight.server import db  # noqa: E402

INTERVIEW_ID = "R046"
DIMENSION_ID = "purchase_attribute"
NEW_VALUE = "增购"

BASIS = (
    "模板题 1 口径为「已婚以小家庭（不含父母）为单位」；Q1 原话说明旧车本田雅阁购入当时仍由妻子使用、"
    "没有卖掉，家庭在购入当时是添置一辆车，属增购；个人视角的「换购」不适用于家庭口径；"
    "interview.purchase_type=增购 交叉一致。"
)

TAG_EVIDENCE = [
    {
        "tag_evidence_id": "TEI-91315ed80cf5faca5d12",
        "time_range": "3055.8-3089.4",
        "quote": "我那个车当时我是我老婆在开，所以我没有卖掉哦……想增购……但是那个车是我老婆还在开，"
                 "所以它属于是对我来说增购，对家对我来说换购，对家庭来说属于增购。",
    }
]

EVIDENCE_REFS = [
    {
        "evidence_id": "EV-6295e417f47cda07a4ab",
        "question_id": 1,
        "start_sec": 3071.7,
        "end_sec": 3072.8,
        "quote": "想增购。",
        "source": "tag_evidence",
    },
    {
        "evidence_id": "EV-978feb41abc39345abbd",
        "question_id": 1,
        "start_sec": 3075.7,
        "end_sec": 3083.6,
        "quote": "但是那个车是我老婆还在开，所以它属于是对我来说增购，对家对我来说换购，对家庭来说属于增购。",
        "source": "tag_evidence",
    },
]


def main() -> int:
    conn = db.connect()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "select a.archive_id, a.template_snapshot, a.coverage_required, a.status,"
                " f.value_text, f.fill_mode, f.review_status, f.no_data_reason,"
                " f.source_ref, f.evidence_refs"
                " from bci.archive a join bci.archive_field f using (archive_id)"
                " where a.interview_id = %s and f.dimension_id = %s"
                " order by a.revision desc limit 1",
                (INTERVIEW_ID, DIMENSION_ID),
            )
            row = cur.fetchone()
            if row is None:
                print("NOT_FOUND", INTERVIEW_ID, DIMENSION_ID)
                return 2
            (archive_id, snapshot, coverage_before, status_before, value_text, fill_mode,
             review_status, reason, source_ref, evidence_refs) = row
            print("BEFORE", json.dumps({
                "archive_id": archive_id, "value_text": value_text, "fill_mode": fill_mode,
                "review_status": review_status, "no_data_reason": reason,
                "coverage_required": str(coverage_before), "status": status_before,
            }, ensure_ascii=False))

            if review_status != "suspect" and value_text == NEW_VALUE:
                existing = (source_ref or {}).get("correction") or {}
                if "from_tag_value" not in existing:
                    existing["from_tag_value"] = "换购；增购。"
                    patched = dict(source_ref or {})
                    patched["correction"] = existing
                    cur.execute(
                        "update bci.archive_field set source_ref = %s, updated_at = now()"
                        " where archive_id = %s and dimension_id = %s",
                        (Json(patched), archive_id, DIMENSION_ID),
                    )
                    conn.commit()
                    print("BACKFILL from_tag_value")
                else:
                    print("SKIP_ALREADY_CORRECTED")
                return 0

            correction = {
                "from_value": value_text,
                "from_tag_value": "换购；增购。",
                "from_fill_mode": fill_mode,
                "from_review_status": review_status,
                "from_no_data_reason": reason,
                "to_value": NEW_VALUE,
                "corrected_at": datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"),
                "corrected_by": "TRAE",
                "basis": BASIS,
                "rule": "模板题 1：已婚以小家庭（不含父母）为单位",
                "answer_id": "A-R046-Q001",
                "purchase_type_metadata": "增购",
                "tag_evidence": TAG_EVIDENCE,
            }
            new_source_ref = dict(source_ref or {})
            new_source_ref["correction"] = correction

            cur.execute(
                "update bci.archive_field set value_text = %s, fill_mode = 'tag',"
                " review_status = 'ok', no_data_reason = null,"
                " source_ref = %s, evidence_refs = %s, updated_at = now()"
                " where archive_id = %s and dimension_id = %s",
                (NEW_VALUE, Json(new_source_ref), Json(EVIDENCE_REFS), archive_id, DIMENSION_ID),
            )

            # 与生成器一致：required 维中“有值”的占比
            required = {
                d["id"] for d in snapshot.get("dimensions", []) if d.get("required", True)
            }
            cur.execute(
                "select dimension_id, value_text, value_json from bci.archive_field"
                " where archive_id = %s",
                (archive_id,),
            )
            filled = 0
            for dim_id, v_text, v_json in cur.fetchall():
                if dim_id in required and (v_text not in (None, "") or v_json not in (None, "", [], {})):
                    filled += 1
            coverage = round(filled / len(required) * 100, 2) if required else 0.0
            status = "ready" if filled == len(required) else "partial"
            cur.execute(
                "update bci.archive set coverage_required = %s, status = %s, updated_at = now()"
                " where archive_id = %s",
                (coverage, status, archive_id),
            )
            print("AFTER", json.dumps({
                "value_text": NEW_VALUE, "fill_mode": "tag", "review_status": "ok",
                "coverage_required": coverage, "status": status,
                "required_total": len(required), "required_filled": filled,
            }, ensure_ascii=False))
        conn.commit()
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
