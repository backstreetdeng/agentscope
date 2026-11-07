"""生成器枚举归一联调（只读、不调模型、不落库）。

直接对真实库的 R063（实际增购。）与 R046（换购；增购。）跑 `_tag_field`，
确认 purchase_attribute 分别落「增购 / normalized」与「无值 / suspect」。
"""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT))

from competitor_insight.server import db  # noqa: E402
from competitor_insight.server.archive_generator import ArchiveGenerator, PostgresInterviewSource  # noqa: E402

generator = ArchiveGenerator(PostgresInterviewSource(db.connect))
dim = next(d for d in generator.source_map.dimensions if d.dimension_id == "purchase_attribute")

out = {}
for interview_id in ("R063", "R046"):
    bundle = PostgresInterviewSource(db.connect).load(interview_id)
    field = generator._tag_field(dim, bundle)
    out[interview_id] = {
        "raw_tag": [t.value for t in bundle.tags.get("首增换购属性", ())],
        "purchase_type": bundle.interview.get("purchase_type"),
        "fill_mode": field.fill_mode,
        "value_text": field.value_text,
        "review_status": field.review_status,
        "no_data_reason": field.no_data_reason,
        "source_ref": field.source_ref,
    }
    print(json.dumps({interview_id: out[interview_id]}, ensure_ascii=False, indent=2))

(Path(__file__).resolve().parent / "generator_dryrun.json").write_text(
    json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8"
)
