# -*- coding: utf-8 -*-
"""Build from a run-specific, authoritative source package, not old template facts."""
import json
import os
from pathlib import Path
import sys
from macro_engine import build

def main():
    if len(sys.argv)!=5: raise SystemExit("usage: build_macro_report.py <YYYY-MM> <package.json> <output.pptx> <ledger.json>")
    root=Path(os.environ.get("SKILL_RUN_ROOT",Path.cwd())).resolve()
    paths=[(root/p).resolve() for p in sys.argv[2:]]
    if any(root not in p.parents for p in paths): raise ValueError("artifact_path_outside_run")
    package=json.loads(paths[0].read_text(encoding="utf-8"))
    reference=Path(__file__).resolve().parents[1]/"assets/reference.pptx"
    print(json.dumps(build(reference,sys.argv[1],package,paths[1],paths[2],root),ensure_ascii=False))

if __name__=="__main__":
    try: main()
    except Exception as exc:
        print(json.dumps({"passed":False,"issues":[{"code":"typed_build_failed","message":str(exc),"exception":type(exc).__name__}]},ensure_ascii=False))
        raise SystemExit(1)
