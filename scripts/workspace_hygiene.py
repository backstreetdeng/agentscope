"""Read-only project-root inventory. No deletion, moving, network or services.

Run with ../Scripts/python.exe -B scripts/workspace_hygiene.py [--json].
The root is derived from this file, regardless of the caller's working directory.
Exit 1 means an item has no approved placement; review it before changing policy.
"""
from __future__ import annotations

import argparse
import fnmatch
import json
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[1]
POLICY = PROJECT / "docs" / "root-files.json"


def inventory() -> dict:
    policy = json.loads(POLICY.read_text(encoding="utf-8"))
    entries = []
    for path in sorted(PROJECT.iterdir(), key=lambda p: p.name.casefold()):
        category, purpose = "unclassified", "请确认用途并迁入合适目录；不得直接删除"
        if path.is_symlink():
            category, purpose = "unclassified", "链接需单独核实目标，检查器不遍历"
        elif path.is_dir() and path.name in policy["root_directories"]:
            category, purpose = "directory", policy["root_directories"][path.name]
        elif path.is_file():
            if path.name in policy["root_files"]:
                category, purpose = "entry_or_config", policy["root_files"][path.name]
            elif path.name in policy["legacy_pages"]:
                category, purpose = "legacy_page", policy["legacy_pages"][path.name]
            elif any(fnmatch.fnmatchcase(path.name, pattern) for pattern in policy["protected_patterns"]):
                category, purpose = "protected_config", "凭据/环境配置；不读取内容，不作为临时文件清理"
        entries.append(dict(name=path.name, category=category, purpose=purpose))
    unknown = [item["name"] for item in entries if item["category"] == "unclassified"]
    return dict(project=str(PROJECT), policy=str(POLICY), root_files=sum(p.is_file() for p in PROJECT.iterdir()),
                root_directories=sum(p.is_dir() for p in PROJECT.iterdir()), unclassified=unknown,
                passed=not unknown, entries=entries)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true", help="Print full filename/purpose inventory; no file contents")
    args = parser.parse_args()
    result = inventory()
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(f"Root files: {result['root_files']}; root directories: {result['root_directories']}")
        if result["passed"]:
            print("PASS: every root item has a documented purpose.")
        else:
            print("REVIEW: move these items to the correct task directory, or document a justified root entry:")
            for name in result["unclassified"]:
                print("  " + name)
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
