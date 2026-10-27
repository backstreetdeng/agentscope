"""One live configured-model smoke test using synthetic forecast data only.

Loads server credentials without printing them. No browser/service restart.
"""
import asyncio
import contextlib
from datetime import datetime
import io
import json
from pathlib import Path
import sys

PROJECT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(PROJECT))


async def main():
    import app
    output=PROJECT/'outputs/forecast-engine-integration'/('live-'+datetime.now().strftime('%Y%m%d-%H%M%S'))
    output.mkdir(parents=True)
    record={'kind':'live model + real tools, synthetic input only','external_citation_allowed':False}
    # AgentScope may print model reasoning/tool payloads. Do not publish that console stream.
    stream=io.StringIO()
    try:
        with contextlib.redirect_stdout(stream),contextlib.redirect_stderr(stream):
            result=await app.run_agent_once('market_strategy','请调用 run_forecast，选择 base 情景，查询2027年总量的P10/P50/P90。仅使用预测数学工具，不联网。','market_forecast')
        names=[e['name'] for e in result.get('tool_events',[]) if e['status']=='success']
        record.update(tool_calls=names,passed='run_forecast' in names and '禁止对外引用' in result['answer'],
                      run_id=result.get('forecast_engine',{}).get('run_id'),model_provider=result.get('model_provider'),
                      explanation_validated=result.get('forecast_engine',{}).get('explanation_validated'))
        (output/'answer.md').write_text(result['answer'],encoding='utf-8')
    except Exception as exc:
        record.update(passed=False,error_type=type(exc).__name__)
    finally:
        stream.close()
    (output/'verification.json').write_text(json.dumps(record,ensure_ascii=False,indent=2),encoding='utf-8')
    (output/'README.md').write_text('One live LLM tool-selection verification. No secrets or model reasoning retained.\nReproduce: ../Scripts/python.exe -B scripts/verify_forecast_engine_agent.py\nSynthetic values are not real market predictions.\n',encoding='utf-8')
    print(json.dumps(dict(output=str(output),**record),ensure_ascii=False))
    return 0 if record['passed'] else 1


if __name__=='__main__': raise SystemExit(asyncio.run(main()))
