"""CLI wrapper for the project consulting HTML PPT generator."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def find_project_root() -> Path:
    return Path(__file__).resolve().parents[3]


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate a consulting-style HTML PPT from a business report.")
    parser.add_argument("--input", required=True, help="Input report text/Markdown path.")
    parser.add_argument("--output", required=True, help="Output HTML path.")
    parser.add_argument("--title", default="", help="Deck title.")
    args = parser.parse_args()

    project_root = find_project_root()
    sys.path.insert(0, str(project_root))

    from utils.html_ppt_builder import build_consulting_html_ppt

    input_path = Path(args.input)
    output_path = Path(args.output)
    markdown = input_path.read_text(encoding="utf-8")
    result = build_consulting_html_ppt(markdown, args.title or input_path.stem, output_path, project_root)
    result["html_path"] = str(output_path)
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
