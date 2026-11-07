"""生成器渠道归并联调（只读、不调模型、不落库）。

对真实库任选受访者跑 `_tag_field`，确认 value_json 已归并、source_ref 保留原始写法。
"""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT))

from competitor_insight.server import db  # noqa: E402
from competitor_insight.server.archive_generator import ArchiveGenerator, PostgresInterviewSource  # noqa: E402

generator = ArchiveGenerator(PostgresInterviewSource(db.connect))
dim = next(d for d in generator.source_map.dimensions if d.dimension_id == "info_channels")

out = {}
for interview_id in ("R003", "R046"):
    bundle = PostgresInterviewSource(db.connect).load(interview_id)
    field = generator._tag_field(dim, bundle)
    out[interview_id] = {
        "value_json": field.value_json,
        "raw_values": field.source_ref.get("raw_values"),
        "raw_parts": field.source_ref.get("raw_parts"),
        "channel_normalization": field.source_ref.get("channel_normalization"),
    }
    print(json.dumps({interview_id: out[interview_id]}, ensure_ascii=False))

(Path(__file__).resolve().parent / "channel_dryrun.json").write_text(
    json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8"
)
