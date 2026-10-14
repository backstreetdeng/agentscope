from __future__ import annotations

import json
from pathlib import Path
import sys


PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT))

from utils.monthly_report_narrative import apply_narratives_to_ppt  # noqa: E402


SOURCE = PROJECT / "outputs" / "ppt" / "2026年8月中国乘用车市场月度分析报告_AI生成版_20260930_220839.pptx"
NARRATIVE = (
    PROJECT
    / "outputs"
    / "monthly-report-data"
    / "month-20260930-180147-78457578"
    / "narrative_evidence.json"
)
OUTPUT = PROJECT / "outputs" / "ppt" / "2026年8月中国乘用车市场月度分析报告_AI生成版_三行高质量修正版.pptx"


def main() -> None:
    narrative = json.loads(NARRATIVE.read_text(encoding="utf-8"))
    result = apply_narratives_to_ppt(SOURCE, OUTPUT, narrative)
    print(json.dumps({"output": str(OUTPUT), **result}, ensure_ascii=False))


if __name__ == "__main__":
    main()
