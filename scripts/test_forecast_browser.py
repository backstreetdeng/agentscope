"""Opt-in real local-browser acceptance using the supplied business workbook."""
import json
import time
from pathlib import Path
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
SOURCE = Path('D:/document/WXWork/1688852089355778/Cache/File/2026-10/2012起分月PC+NEV销量.xlsx')
OUTPUT = ROOT / 'outputs/forecast-browser-selftest-20261010'


def main():
    OUTPUT.mkdir(parents=True, exist_ok=True)
    evidence = {'checks': [], 'stages': [], 'page_errors': [], 'failed_requests': []}
    def check(name, ok):
        evidence['checks'].append({'name': name, 'passed': bool(ok)})
        if not ok:
            raise AssertionError(name)
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(viewport={'width':1440,'height':1050}, accept_downloads=True, timezone_id='Asia/Shanghai')
        page = context.new_page()
        page.on('pageerror', lambda error: evidence['page_errors'].append(str(error)))
        page.on('requestfailed', lambda request: evidence['failed_requests'].append({'url':request.url,'failure':request.failure}))
        try:
            page.goto('http://127.0.0.1:7860/#forecast', wait_until='networkidle')
            page.locator('.forecast').wait_for(state='visible')
            check('Excel selector accepts xlsx', '.xlsx' in page.locator('#forecast-history-file').get_attribute('accept'))
            page.locator('#forecast-history-unit').select_option('vehicle')
            with page.expect_response(lambda r:'/api/forecast/history?' in r.url and r.request.method=='POST', timeout=60000) as upload_response:
                page.locator('#forecast-history-file').set_input_files(str(SOURCE))
            check('Workbook upload HTTP success', upload_response.value.status == 200)
            page.wait_for_function("document.getElementById('forecast-history-state').textContent.includes('已接入')")
            uploaded = context.request.get('http://127.0.0.1:7860/api/forecast/history').json()
            check('Workbook uploaded via page', uploaded['filename']==SOURCE.name and uploaded['summary']['count']==176)
            evidence['history_id'] = uploaded['history_id']
            page.locator('#forecast-target-year').select_option('2027')
            check('User annual 2060 preserved',page.locator('#forecast-annual-total').input_value()=='2060')
            page.locator('#forecast-prompt').fill('帮我输出2027年1—12月的乘用车总量预测和新能源渗透率，表格形式输出。本次自测按原单位辆、PC含NEV且同口径进行假设试算，年度采用2026年1960万辆、2027年2060万辆；政策与价格驱动尚未量化。')
            with page.expect_response(lambda r:r.url.endswith('/api/forecast/jobs') and r.request.method=='POST',timeout=60000) as run_response:
                page.locator('.forecast-run').click()
            check('Run start HTTP success', run_response.value.status == 202)
            job = context.request.get('http://127.0.0.1:7860/api/forecast/jobs?latest=1').json()
            check('Run started by browser click', bool(job.get('run_id')))
            evidence['run_id'] = run_id = job['run_id']
            print(json.dumps({'run_id':run_id,'status':job['status']},ensure_ascii=False),flush=True)
            deadline=time.monotonic()+480
            last=''
            while time.monotonic()<deadline:
                response=context.request.get('http://127.0.0.1:7860/api/forecast/jobs', params={'run_id':run_id},timeout=30000)
                check('Status endpoint returns JSON',response.status==200)
                job=response.json()
                phase=(job['status'],job.get('stage'))
                if phase!=last:
                    event={'status':job['status'],'stage':job.get('stage'),'time':time.time()}
                    evidence['stages'].append(event)
                    print(json.dumps(event,ensure_ascii=False),flush=True)
                    last=phase
                if job['status'] in ('completed','failed'):
                    break
                page.wait_for_timeout(1200)
            evidence['job']=job
            check('Forecast completed',job['status']=='completed')
            check('Independent validators passed',job['validation']['status']=='passed')
            check('2060 annual closure',abs(sum(r['total'] for r in job['result']['rows'])-2060)<1e-7)
            page.wait_for_function("document.querySelectorAll('#forecast-table-body tr').length === 12",timeout=15000)
            check('Page annual KPI',page.locator('#forecast-total').inner_text()=='2,060.00')
            check('Page weighted penetration',page.locator('#forecast-penetration').inner_text()==format(job['result']['summary']['penetration'],'.2f'))
            for row in job['result']['rows']:
                cells=page.locator('#forecast-table-body tr').nth(row['month']-1).locator('td').all_inner_texts()
                check('Displayed month '+str(row['month']),format(row['total'],',.2f')==cells[1] and format(row['penetration'],'.2f')+'%'==cells[2])
            check('Office and CSV downloads shown',page.locator('#forecast-artifacts a').count()==3)
            for link in page.locator('#forecast-artifacts a').all():
                with page.expect_download(timeout=30000) as download_response:
                    link.click()
                download=download_response.value
                downloaded=OUTPUT/download.suggested_filename
                download.save_as(str(downloaded))
                check('Browser downloaded '+downloaded.suffix,downloaded.stat().st_size>100)
            page.locator('.forecast').screenshot(path=str(OUTPUT/'forecast-result.png'),timeout=30000)
            page.reload(wait_until='networkidle')
            page.wait_for_function("document.querySelectorAll('#forecast-table-body tr').length===12",timeout=20000)
            check('Reload restores identical run',run_id in page.locator('#forecast-job-id').inner_text())
            check('Reload restores history',SOURCE.name in page.locator('#forecast-history-summary').inner_text())
            check('No JavaScript errors',not evidence['page_errors'])
            evidence['status']='passed'
            print(json.dumps({'status':'passed','checks':len(evidence['checks']),'output':str(OUTPUT)},ensure_ascii=False),flush=True)
        except Exception as error:
            evidence.update(status='failed',error=str(error))
            page.screenshot(path=str(OUTPUT/'failure.png'),full_page=True)
            raise
        finally:
            (OUTPUT/'browser-acceptance.json').write_text(json.dumps(evidence,ensure_ascii=False,indent=2),encoding='utf-8')
            context.close()
            browser.close()


if __name__=='__main__':
    main()
