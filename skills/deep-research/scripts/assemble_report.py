"""深度调研报告分段合并器（deep-research Skill）。

用途：模型单轮输出长度有限，长报告按段写入 working/report-parts/（文件名需可排序，
如 01-summary.md、02-body.md、03-sources.md），本脚本按文件名顺序合并为单一交付文件
outputs/research-report.md，绕开单次写入截断。

输入：无参数（固定目录约定）
输出：合并后的 outputs/research-report.md；stdout 结构化 JSON
副作用：覆盖写入 outputs/research-report.md（仅限本次隔离运行工作区内）
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path


def main() -> int:
    run_root = Path(os.environ["SKILL_RUN_ROOT"]) if "SKILL_RUN_ROOT" in os.environ else Path.cwd()
    parts_dir = run_root / "working" / "report-parts"
    if not parts_dir.is_dir():
        print(json.dumps({"passed": False, "failures": [f"分段目录不存在：{parts_dir}"]}, ensure_ascii=False))
        return 2
    parts = sorted(item for item in parts_dir.glob("*.md") if item.is_file())
    if not parts:
        print(json.dumps({"passed": False, "failures": ["working/report-parts/ 下没有任何 .md 分段文件。"]}, ensure_ascii=False))
        return 2
    merged = "\n\n".join(item.read_text(encoding="utf-8-sig").strip() for item in parts)
    if len(merged.strip()) < 300:
        print(json.dumps({"passed": False, "failures": [f"合并后正文过短（{len(merged.strip())} 字符）。"]}, ensure_ascii=False))
        return 1
    out = run_root / "outputs" / "research-report.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(merged, encoding="utf-8")
    print(json.dumps({
        "passed": True,
        "merged_parts": [item.name for item in parts],
        "output": "outputs/research-report.md",
        "bytes": out.stat().st_size,
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    import os
    sys.exit(main())
