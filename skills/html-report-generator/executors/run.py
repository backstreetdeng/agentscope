#!/usr/bin/env python3
"""
executors/run.py - html-report-generator skill 执行入口

参照架构 v1.0 (2026-06-23) - 4.1 SKILL.md 标准结构
每个 Skill 目录下必须有 executors/run.py 作为标准执行入口
"""
import sys
import json
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SKILL_DIR))


def main():
    """
    标准执行入口
    用法: python executors/run.py <markdown_path> <html_output_path>
          python executors/run.py --json '{"markdown_path":"...","html_output_path":"..."}'
    """
    if len(sys.argv) < 3:
        print(json.dumps({
            "success": False,
            "error": "参数不足",
            "usage": "python executors/run.py <markdown_path> <html_output_path>"
        }, ensure_ascii=False))
        return 1

    if sys.argv[1] == "--json":
        params = json.loads(sys.argv[2])
        md_path = params.get("markdown_path")
        out_path = params.get("html_output_path")
    else:
        md_path = sys.argv[1]
        out_path = sys.argv[2]

    try:
        from html_report_generator import generate_from_markdown
        result = generate_from_markdown(
            markdown_path=md_path,
            output_path=out_path,
        )
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except Exception as e:
        print(json.dumps({
            "success": False,
            "error": str(e),
            "markdown_path": md_path,
            "html_output_path": out_path,
        }, ensure_ascii=False))
        return 2


if __name__ == "__main__":
    sys.exit(main())