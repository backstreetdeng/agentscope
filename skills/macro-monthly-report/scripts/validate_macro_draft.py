"""Independent source replay and native-cell acceptance, never formal acceptance."""
import json
import os
from pathlib import Path
import sys
from macro_engine import validate


def main():
    if len(sys.argv) != 3: raise SystemExit("usage: validate_macro_draft.py <report.pptx> <ledger.json>")
    root = Path(os.environ.get("SKILL_RUN_ROOT", Path.cwd())).resolve()
    paths = [(root / p).resolve() for p in sys.argv[1:]]
    if any(not p.is_relative_to(root) or p == root for p in paths): raise ValueError("artifact_path_outside_run")
    result = validate(*paths, _public_draft=True)
    print(json.dumps(result, ensure_ascii=False))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
