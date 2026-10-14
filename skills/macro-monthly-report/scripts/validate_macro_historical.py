import json,sys,os
from pathlib import Path
from macro_historical_engine import validate
if __name__=='__main__':
    try:
        root=Path(os.environ.get('SKILL_RUN_ROOT',Path.cwd())).resolve()
        paths=[(root/p).resolve() for p in sys.argv[1:3]]
        if any(root not in p.parents for p in paths):raise ValueError('artifact_outside_run')
        result=validate(*paths)
    except Exception as exc:result={'passed':False,'issues':[{'code':'historical_validation_failed','message':str(exc)}]}
    print(json.dumps(result,ensure_ascii=False));raise SystemExit(0 if result['passed'] else 1)
