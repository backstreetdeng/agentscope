"""Exercise the four real engine tools in a private task, without any model/API."""
import asyncio
from datetime import datetime
import hashlib
import json
from pathlib import Path
import sys

PROJECT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(PROJECT))
from integrations.forecast_engine_runtime import ForecastEngineSession, render_answer


async def main():
    source=PROJECT/'forecast-engine'
    names=['data/retail_monthly.csv','data/province_monthly.csv','data/events.csv','db/market.db']
    digest=lambda:{n:hashlib.sha256((source/n).read_bytes()).hexdigest() for n in names}
    before=digest(); session=ForecastEngineSession()
    requests=[('query_indicator',dict(powertrain='bev',start='2026-07',end='2026-09')),
              ('run_forecast',dict(scenario='base')),
              ('adjust_scenario',dict(event_id='tax_last_train_2027h2',mult=1.10)),
              ('explain_forecast',dict(ym='2027-12',powertrain='total',scenario='base'))]
    checks=[]
    for name,args in requests:
        result=await session.call(name,args)
        if not result.get('ok'): raise RuntimeError(str(result))
        checks.append(dict(name=name,ok=True,data_status=result['data']['data_status'],external_citation_allowed=result['data']['external_citation_allowed']))
        print(name+' OK',flush=True)
    answer,passed=render_answer(session,'请解释预测依据')
    if not passed or '决策含义' not in answer or '禁止对外引用' not in answer: raise AssertionError('Missing output gate')
    unchanged=before==digest()
    if not unchanged: raise AssertionError('Source data/database changed')
    root=PROJECT/'outputs/forecast-engine-integration'/('tools-'+datetime.now().strftime('%Y%m%d-%H%M%S'))
    root.mkdir(parents=True)
    record=dict(checks=checks,source_unchanged=unchanged,source_sha256=before,run_id=session.run_id,
                model_used=False,expected_scope='synthetic internal pipeline verification only')
    (root/'verification.json').write_text(json.dumps(record,ensure_ascii=False,indent=2),encoding='utf-8')
    (root/'answer.md').write_text(answer,encoding='utf-8')
    (root/'README.md').write_text('Real four-tool integration test; no LLM or external API.\nReproduce: ../Scripts/python.exe -B scripts/verify_forecast_engine_tools.py\nKeep receipt references until acceptance review.\n',encoding='utf-8')
    print(json.dumps(dict(output=str(root),source_unchanged=unchanged,run_id=session.run_id),ensure_ascii=False))


if __name__=='__main__': asyncio.run(main())
