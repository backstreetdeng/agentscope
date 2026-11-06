"""D3 真实库单人生成探查（只读）。

对 R003 / R001 / R002 用真实 user_insight.* 数据跑 ArchiveGenerator；
LLM 用确定性 stub（从 prompt 里取第一个真实证据 ID），只为验证：
- 真实数据能构造 43 维草稿；
- 8 个无来源维落 no_source_reason；
- 满意度三态（区间 / 描述性 / 无分数）；
- 证据由服务端从库内截取，不是模型文本。

不写任何业务表，仅 SELECT；结果写 generate-probe.log。
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(PROJECT_ROOT))

from competitor_insight.server import db  # noqa: E402
from competitor_insight.server.archive_generator import ArchiveGenerator, PostgresInterviewSource  # noqa: E402

OUT = Path(__file__).resolve().parent / "generate-probe.log"
TARGETS = ("R003", "R001", "R002")


def stub_llm(prompt: str) -> str:
    ids = re.findall(r"证据ID：([^\n]+)", prompt)
    first = ids[0].split(",")[0].strip() if ids else ""
    return json.dumps({"value": "（stub 归纳值）", "evidence_ids": [first]}, ensure_ascii=False)


def main() -> int:
    db.load_env()
    generator = ArchiveGenerator(PostgresInterviewSource(db.connect), llm=stub_llm, model="stub-d3")
    lines: list[str] = []
    for interview_id in TARGETS:
        draft = generator.generate(interview_id)
        counts: dict[str, int] = {}
        for field in draft.fields:
            counts[field.fill_mode] = counts.get(field.fill_mode, 0) + 1
        evidence = sum(len(f.evidence_refs) for f in draft.fields)
        quotes = [f.evidence_refs[0]["quote"][:40] for f in draft.fields if f.evidence_refs]
        satisfaction = next(f for f in draft.fields if f.dimension_id == "satisfaction_score")
        none_dims = [f.dimension_id for f in draft.fields if f.fill_mode == "none"]
        lines += [
            f"[{interview_id}] fields={len(draft.fields)} status={draft.status} coverage={draft.coverage_required}",
            f"  fill_mode={counts} evidence_refs={evidence}",
            f"  satisfaction: fill_mode={satisfaction.fill_mode} reason={satisfaction.no_data_reason} "
            f"value={satisfaction.value_text} json={satisfaction.value_json}",
            f"  none_dims({len(none_dims)})={none_dims}",
            f"  quote_samples={quotes[:3]}",
        ]
    OUT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))
    return 0


if __name__ == "__main__":
    sys.exit(main())
