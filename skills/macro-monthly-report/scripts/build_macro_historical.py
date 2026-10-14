import json,os,sys
from pathlib import Path
from macro_historical_engine import build
if __name__=='__main__':
    root=Path(os.environ.get('SKILL_RUN_ROOT',Path.cwd())).resolve()
    if len(sys.argv)!=5:raise SystemExit('usage: build_macro_historical.py MONTH PACKAGE OUTPUT LEDGER')
    paths=[(root/p).resolve() for p in sys.argv[2:]]
    if any(root not in p.parents for p in paths):raise ValueError('artifact_outside_run')
    package=json.loads(paths[0].read_text(encoding='utf-8'))
    print(json.dumps(build(sys.argv[1],package,paths[1],paths[2],root),ensure_ascii=False))
