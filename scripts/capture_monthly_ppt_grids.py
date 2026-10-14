"""Bounded read-only supplement for PPT rows missing from a saved BI package."""
import asyncio
from datetime import datetime
import json
from pathlib import Path
import sys
from hashlib import sha256

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools.monthly_report_browser import MonthlyReportBrowserConnector, SOURCE_CARD_CODE_ALIASES
from playwright.async_api import async_playwright


async def capture(page, code, month):
    aliases = [code, *SOURCE_CARD_CODE_ALIASES.get(code, ())]
    await page.evaluate('''cfg => {
      const title=[...document.querySelectorAll('[data-open="title"]')].find(e=>cfg.aliases.some(c=>e.innerText.startsWith(c+'：')||e.innerText.startsWith(c+':')));
      if(!title) throw new Error('Missing card '+cfg.code);
      let best=title;
      for(let n=title.parentElement;n;n=n.parentElement){
        const codes=[...new Set(n.innerText.match(/P\\d+(?:[.-]\\d+)*(?:[A-Z])?/g)||[])];
        if(codes.length!==1)break;best=n;
      }
      best.setAttribute('data-ppt-grid-card',cfg.code);
    }''', {'code': code, 'aliases': aliases})
    root = page.locator(f'[data-ppt-grid-card="{code}"]')
    await root.scroll_into_view_if_needed(timeout=5000)
    more = root.get_by_text('加载更多', exact=True)
    if await more.count():
        await more.click(timeout=5000)
        await asyncio.sleep(.5)
    scroller = root.locator('.fast-sub-table.BR').first
    metrics = await scroller.evaluate('e=>({height:e.scrollHeight,client:e.clientHeight,width:e.scrollWidth,cw:e.clientWidth})')
    headers, cells = {}, {}
    max_y = max(0, metrics['height']-metrics['client'])
    step = max(35, int(metrics['client']*.8))
    positions = list(range(0, int(max_y)+1, step)) + [max_y]
    if len(positions)>350:
        raise ValueError(f'{code}行窗口超出安全补采范围，需更小的源表筛选。')
    max_x = max(0, metrics['width']-metrics['cw'])
    xs = list(range(0, int(max_x)+1, max(80,int(metrics['cw']*.8))))+[max_x]
    for y in positions:
        for x in sorted(set(xs)):
            await scroller.evaluate('(e,pos)=>{e.scrollTo({top:pos.y,left:pos.x,behavior:"instant"});e.dispatchEvent(new Event("scroll",{bubbles:true}));}', {'y':y,'x':x})
            await asyncio.sleep(.06)
            snapshot = await root.evaluate('''e => ({
              headers:[...e.querySelectorAll('.fast-sub-table.TR [data-row][data-col]')].map(c=>({row:+c.dataset.row,col:+c.dataset.col,text:c.innerText.trim()})),
              cells:[...e.querySelectorAll('.fast-sub-table.BR [data-row][data-col]')].map(c=>({row:+c.dataset.row,col:+c.dataset.col,text:c.innerText.trim()}))})''')
            for target, rows in ((headers,snapshot['headers']),(cells,snapshot['cells'])):
                for cell in rows:
                    key=(cell['row'],cell['col'])
                    if key in target and target[key]['text']!=cell['text']:
                        raise ValueError(f'{code}滚动中同一单元格发生冲突。')
                    target[key]=cell
    await scroller.evaluate('e=>{e.scrollTo({top:0,left:0,behavior:"instant"});e.dispatchEvent(new Event("scroll",{bubbles:true}));}')
    grid={'headers':[headers[k] for k in sorted(headers)],'cells':[cells[k] for k in sorted(cells)],
          'month':month,'complete':True,'strategy':'visible_dom_cell_boundaries','windows':len(positions)*len(xs)}
    return grid


async def main(source, output, codes=None):
    source_data=source.read_bytes()
    package=json.loads(source_data)
    if output.is_file():
        saved=json.loads(output.read_text(encoding='utf-8'))
        if saved.get('ppt_grid_supplement',{}).get('source_sha256')==sha256(source_data).hexdigest():
            package=saved
    connector=MonthlyReportBrowserConnector()
    connector._assert_session_owner()
    runtime=await async_playwright().start()
    browser=await runtime.chromium.connect_over_cdp(connector.cdp_endpoint,timeout=10000)
    pages=[p for c in browser.contexts for p in c.pages if p.url == connector.source_url]
    if len(pages)!=1:raise ValueError('未找到唯一的已有月报BI页面；未打开新浏览器。')
    connector._direct_page=pages[0]
    connector._browser=browser
    status=await connector._quick_page_status()
    if not status.get('page_ready'):raise ValueError('已登录BI页面未就绪。')
    output.parent.mkdir(parents=True,exist_ok=True)
    selected = codes or ('P2-8.1','P2-3.3B','P2-4.3B','P2-14.2','P2-3.3A','P2-4.3A','P2-14.1','P2-10.1','P2-10.2','P2-13.1','P2-13.2')
    for code in selected:
        card=next(c for c in package['cards'] if c['code']==code)
        if card.get('grid_snapshot',{}).get('complete'):
            continue
        grid=await asyncio.wait_for(capture(pages[0],code,package['report_month']),timeout=120)
        card=next(c for c in package['cards'] if c['code']==code)
        card['grid_snapshot']=grid
        flat='\n'.join(c['text'] for c in grid['headers']+grid['cells'] if c['text'])
        card['text']+='\n---视图分段---\n'+code+'：PPT逐单元格补采\n'+flat
        package['ppt_grid_supplement']={'source_package':str(source),'captured_at':datetime.now().isoformat(),
                                        'source_sha256':sha256(source_data).hexdigest(),'contains_credentials':False}
        package['snapshot_path']=str(output.resolve())
        output.write_text(json.dumps(package,ensure_ascii=False,indent=2),encoding='utf-8')
        print(code,'saved',len({c['row'] for c in grid['cells']}),'rows',flush=True)
    # Disconnect this driver only; never close the user's Chrome.
    await runtime.stop()
    diagnostics = connector._card_diagnostics({c['code']:c['text'] for c in package['cards']},package['report_month'])
    package['card_validation'] = diagnostics
    package['delayed_cards'] = [c for c,d in diagnostics.items() if d['status']=='delayed_allowed']
    package['cards_usable'] = sum(d['status'] in ('valid','delayed_allowed') for d in diagnostics.values())
    package['generation_ready'] = package['cards_usable']==package['cards_expected']
    package['captured_at'] = datetime.now().isoformat()
    package['code'] = 'data_package_ready' if package['generation_ready'] else 'data_package_incomplete'
    output.write_text(json.dumps(package,ensure_ascii=False,indent=2),encoding='utf-8')
    print('delayed_cards',package['delayed_cards'],flush=True)


if __name__=='__main__':
    asyncio.run(main(Path(sys.argv[1]),Path(sys.argv[2]),sys.argv[3].split(',') if len(sys.argv)>3 else None))
