"""Local-only end-to-end oil test in a fresh headless browser and own server.

Creates a unique evidence directory; never touches 7860 or existing browsers.
All browser requests to non-local hosts are blocked. Does not call an LLM.
"""
from pathlib import Path
import json
import os
import subprocess
import sys
import time
from uuid import uuid4

PROJECT=Path(__file__).resolve().parents[1]


def main():
    import httpx
    from playwright.sync_api import sync_playwright
    out=PROJECT/'outputs'/'chronos-003'/('browser-oil-'+uuid4().hex)
    out.mkdir(parents=True)
    report=dict(status='running',retention='内部浏览器验收证据，清理前确认引用。',external_model_calls=False)
    result_path=out/'manifest.json'
    result_path.write_text(json.dumps(report),encoding='utf-8')
    base='http://127.0.0.1:8874'
    log=(out/'server.log').open('w',encoding='utf-8')
    env=os.environ.copy();env['PYTHONIOENCODING']='utf-8';env['HF_HUB_OFFLINE']='1';env['TRANSFORMERS_OFFLINE']='1'
    server=subprocess.Popen([sys.executable,'-B','scripts/preview_forecast_engine.py','--port','8874','--no-agent-loop'],
        cwd=PROJECT,env=env,stdout=log,stderr=log,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    try:
        with httpx.Client(base_url=base,trust_env=False,timeout=5,headers={'Origin':base}) as client:
            for _ in range(45):
                if server.poll() is not None:raise RuntimeError('预览服务启动失败，见server.log')
                try:
                    if client.get('/forecast-engine-view').status_code==200:break
                except httpx.TransportError:pass
                time.sleep(1)
            else:raise RuntimeError('预览启动超时')
            bad=client.post('/api/forecast-engine/sarimax-jobs',json=dict(operation='forecast',province='上海',energy='插电式混合动力',horizon=6,profile='gd_oil'))
            assert bad.status_code==400
            report['wrong_region_rejected']=True
        with sync_playwright() as p:
            browser=p.chromium.launch(headless=True,channel='msedge')
            page=browser.new_page(viewport={'width':1440,'height':1000})
            page.route('**/*',lambda route: route.continue_() if route.request.url.startswith(base+'/') else route.abort())
            page.goto(base+'/#forecast-engine')
            page.wait_for_function("document.querySelector('#nf-run') && !document.querySelector('#nf-run').disabled",timeout=60000)
            page.select_option('#nf-forecast-model','oil')
            page.select_option('#nf-chronos-region','广东');page.select_option('#nf-chronos-energy','插电式混合动力')
            page.click('#nf-run')
            page.wait_for_function("document.querySelector('#nf-state-text').textContent === '结果已生成' || document.querySelector('#nf-state-text').textContent === '本次操作未完成'",timeout=120000)
            assert page.locator('#nf-state-text').inner_text()=='结果已生成',page.locator('#nf-state-detail').inner_text()
            assert '广东92号' in page.locator('#nf-result-meta').inner_text()
            assert page.locator('#nf-result-table tbody tr').count()==6
            page.screenshot(path=str(out/'forecast.png'),full_page=True)
            with page.expect_download() as dl:page.click('#nf-download')
            receipt=dl.value;receipt.save_as(str(out/'download.json'))
            run=json.loads((out/'download.json').read_text(encoding='utf-8'))['run_id']
            with httpx.Client(base_url=base,trust_env=False,headers={'Origin':base}) as c:
                assert c.post('/api/forecast-engine/deepseek-insights',json=dict(run_id=run,intent='strategy',model='flash')).status_code==400
            report['forecast_job']=run;report['external_assistant_rejected']=True
            page.reload()
            page.wait_for_function("document.querySelector('#nf-result-content') && !document.querySelector('#nf-result-content').hidden",timeout=60000)
            assert page.locator('#nf-forecast-model').input_value()=='oil'
            report['refresh_restores_oil']=True
            page.select_option('#nf-chronos-region','上海')
            assert page.locator('#nf-result-content').is_hidden()
            page.select_option('#nf-chronos-region','广东')
            page.click('[data-nf-mode="chronos-backtest"]');page.click('#nf-run')
            page.wait_for_function("document.querySelector('#nf-state-text').textContent === '结果已生成' || document.querySelector('#nf-state-text').textContent === '本次操作未完成'",timeout=240000)
            assert page.locator('#nf-state-text').inner_text()=='结果已生成',page.locator('#nf-state-detail').inner_text()
            assert '共同窗口模型比较' in page.locator('#nf-result-table').inner_text()
            assert '12个起点数值检查全部成功' in page.locator('#nf-result-table').inner_text()
            assert '不建议启用油价预测' in page.locator('#nf-result-table').inner_text()
            report['numerical_success_and_accuracy_failure_distinct']=True
            page.screenshot(path=str(out/'backtest.png'),full_page=True)
            report['backtest_ui']=True
            browser.close()
        report['status']='passed'
    except Exception as exc:
        report.update(status='failed',error=str(exc));raise
    finally:
        server.terminate();server.wait(timeout=15);log.close()
        result_path.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
        print(str(result_path),flush=True)


if __name__=='__main__':main()
