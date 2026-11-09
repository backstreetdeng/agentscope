"""深度调研报告独立验收器（deep-research Skill / MKT-002）。

输入：
  argv[1]  报告 Markdown 路径（契约：assets/report-contract.json）
输出：
  stdout  结构化结果 JSON：{"passed": bool, "failures": [...]}
  退出码  0=通过；1=验收失败；2=用法错误
副作用：无（只读校验）

规则实现见 utils/research_report_validation.py；契约见 assets/report-contract.json。
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

# skill 包目录带连字符，作为独立脚本执行时需手动定位项目根以导入 utils。
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from utils.research_report_validation import validate_research_report


def main() -> int:
    if len(sys.argv) < 2:
        print("usage: validate_report.py <research-report.md>", file=sys.stderr)
        return 2
    report_path = Path(sys.argv[1])
    # skill runtime 以隔离工作区为 cwd 执行，相对参数按 SKILL_RUN_ROOT 解析。
    if not report_path.is_absolute():
        run_root = os.environ.get("SKILL_RUN_ROOT")
        if run_root:
            report_path = Path(run_root) / report_path
    if not report_path.is_file():
        print(json.dumps({"passed": False, "failures": [f"报告文件不存在：{report_path}"]}, ensure_ascii=False))
        return 2
    failures = validate_research_report(report_path.read_text(encoding="utf-8-sig"))
    print(json.dumps({"passed": not failures, "failures": failures}, ensure_ascii=False))
    return 0 if not failures else 1


if __name__ == "__main__":
    sys.exit(main())
