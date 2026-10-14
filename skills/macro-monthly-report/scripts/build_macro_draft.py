"""Build only an explicitly selected public-data draft in its isolated run."""
import json
import os
from pathlib import Path
import sys
from macro_draft import build_draft


def main():
    if len(sys.argv) != 5:
        raise SystemExit("usage: build_macro_draft.py <YYYY-MM> <package.json> <output.pptx> <ledger.json>")
    root = Path(os.environ.get("SKILL_RUN_ROOT", Path.cwd())).resolve()
    paths = [(root / p).resolve() for p in sys.argv[2:]]
    if any(not p.is_relative_to(root) or p == root for p in paths): raise ValueError("artifact_path_outside_run")
    package = json.loads(paths[0].read_text(encoding="utf-8"))
    reference = Path(__file__).resolve().parents[1] / "assets/reference.pptx"
    print(json.dumps(build_draft(reference, sys.argv[1], package, paths[1], paths[2], root), ensure_ascii=False))


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(json.dumps({"passed": False, "issues": [{"code": "public_draft_build_failed", "message": str(exc)}]}, ensure_ascii=False))
        raise SystemExit(1)
