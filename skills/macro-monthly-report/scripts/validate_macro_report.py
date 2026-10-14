# -*- coding: utf-8 -*-
import json
import sys
from pathlib import Path
from macro_engine import validate

if __name__=="__main__":
    try:
        if len(sys.argv)!=3: raise ValueError("usage: validate_macro_report.py <pptx> <ledger.json>")
        result=validate(sys.argv[1],sys.argv[2])
    except Exception as exc:
        result={"passed":False,"gate":"macro_business","issues":[{"code":"validator_failed","message":str(exc),"exception":type(exc).__name__}]}
    full=Path(sys.argv[2]).parent/"macro-business-validation-full.json" if len(sys.argv)==3 else None
    if full:
        full.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding="utf-8")
        result={**result,"issue_count":len(result.get("issues",[])),"issues":result.get("issues",[])[:25],"full_report":str(full)}
    print(json.dumps(result,ensure_ascii=False))
    raise SystemExit(0 if result["passed"] else 1)
