// 离线浏览器验证：逐页布局、资源、控制、讲稿、演讲者视图与不同视口。
const fs = require('node:fs');
const path = require('node:path');
const {pathToFileURL} = require('node:url');
const {chromium} = require('playwright');
const sharp = require('sharp');
const root = path.dirname(__dirname);
const manifest = JSON.parse(fs.readFileSync(path.join(root,'source-map.json'),'utf8'));
const qa = path.join(root,'qa');
fs.mkdirSync(path.join(qa,'screenshots'),{recursive:true});

async function inspect(page) {
  return page.evaluate(() => {
    const slide = document.querySelector('.deck > .slide.is-active');
    const rect = slide.getBoundingClientRect();
    const scale = rect.width / 1920;
    const errors = [];
    const content = slide.querySelector('.content');
    const cr = content.getBoundingClientRect();
    const footer = slide.querySelector('.deck-footer').getBoundingClientRect();
    const toolbar = document.querySelector('.toolbar').getBoundingClientRect();
    if(rect.bottom>toolbar.top+1) errors.push({kind:'toolbar-overlap',label:'画布应在控制栏上方'});
    for(const el of slide.querySelectorAll('h1,h2,h3,p,li,th,td,.node,.takeaway,.signal,.quote,.review-output,.flat,.panel,.cell,.col')) {
      if(el.closest('.notes')) continue;
      const r = el.getBoundingClientRect();
      const css = getComputedStyle(el);
      if(css.display === 'none' || !r.width || !r.height) continue;
      const label=el.textContent.trim().slice(0,60);
      if(r.left < rect.left-1 || r.right > rect.right+1 || r.top < rect.top-1 || r.bottom > rect.bottom+1) errors.push({kind:'off-canvas',label});
      if(el.closest('.content') && r.bottom > footer.top-15*scale) errors.push({kind:'footer-overlap',label});
      if(el.closest('.content') && r.bottom > cr.bottom+2) errors.push({kind:'body-overflow',label});
      if(el.clientHeight>0 && el.scrollHeight>el.clientHeight+3 && css.display!=='inline') errors.push({kind:'vertical-overflow',label,scroll:el.scrollHeight,client:el.clientHeight});
      if(el.clientWidth>0 && el.scrollWidth>el.clientWidth+3) errors.push({kind:'horizontal-overflow',label});
    }
    return {title:slide.dataset.title,errors,canvas:{x:rect.x,y:rect.y,width:rect.width,height:rect.height}};
  });
}

(async()=>{
  const browser = await chromium.launch({channel:'chrome',headless:true});
  const results=[];
  try {
    for(const deck of manifest) {
      const context=await browser.newContext({viewport:{width:1920,height:1080},deviceScaleFactor:1});
      const page=await context.newPage();
      const consoleErrors=[], failedRequests=[], networkRequests=[];
      page.on('pageerror',e=>consoleErrors.push(String(e)));
      page.on('requestfailed',r=>failedRequests.push({url:r.url(),error:r.failure()?.errorText}));
      page.on('request',r=>{if(/^https?:/.test(r.url()))networkRequests.push(r.url());});
      const url=pathToFileURL(path.join(root,deck.file)).href;
      await page.goto(url);
      await page.waitForSelector('.deck > .slide.is-active');
      await page.evaluate(()=>document.fonts.ready);
      const checks=[];
      for(const [width,height] of [[1920,1080],[1366,768],[390,844]]) {
        await page.setViewportSize({width,height});
        for(let i=1;i<=deck.pages;i++) {
          await page.evaluate(n=>{location.hash='#/'+n},i);
          await page.waitForTimeout(280);
          const check=await inspect(page);
          checks.push({page:i,viewport:`${width}x${height}`,...check});
          if(width===1920) await page.screenshot({path:path.join(qa,'screenshots',`${deck.id}-${String(i).padStart(2,'0')}.png`)});
          if(width===390 && i===1) await page.screenshot({path:path.join(qa,`${deck.id}-mobile.png`)});
        }
      }
      await page.setViewportSize({width:1366,height:768});
      await page.keyboard.press('Home');
      await page.getByRole('button',{name:'下一页',exact:true}).click();
      if(!page.url().endsWith('#/2')) throw Error('Next toolbar navigation failed');
      await page.getByRole('button',{name:'上一页',exact:true}).click();
      if(!page.url().endsWith('#/1')) throw Error('Previous toolbar navigation failed');
      await page.getByRole('button',{name:'讲稿',exact:true}).click();
      await page.waitForSelector('.notes-overlay.open');
      await page.screenshot({path:path.join(qa,`${deck.id}-notes.png`)});
      await page.keyboard.press('Escape');
      await page.getByRole('button',{name:'页面总览',exact:true}).click();
      await page.waitForSelector('.overview.open');
      await page.waitForTimeout(200);
      await page.screenshot({path:path.join(qa,`${deck.id}-overview.png`)});
      await page.locator('.overview .thumb').nth(3).click();
      if(!page.url().endsWith('#/4')) throw Error('Overview navigation failed');
      const popupPromise=page.waitForEvent('popup');
      await page.getByRole('button',{name:'演讲者视图',exact:true}).click();
      const popup=await popupPromise;
      popup.on('pageerror',e=>consoleErrors.push('presenter: '+String(e)));
      await popup.waitForSelector('iframe');
      await popup.waitForTimeout(1000);
      const frameTitles=await Promise.all(popup.frames().filter(f=>f!==popup.mainFrame()).map(f=>f.locator('.deck > .slide.is-active').getAttribute('data-title')));
      if(frameTitles[0]!==deck.slides[3].title || frameTitles[1]!==deck.slides[4].title) throw Error('Presenter previews mismatch: '+JSON.stringify(frameTitles));
      await popup.keyboard.press('ArrowRight');
      await page.waitForURL(/#\/5$/,{timeout:5000});
      await popup.screenshot({path:path.join(qa,`${deck.id}-presenter.png`)});
      await popup.close();
      await page.getByRole('button',{name:'全屏',exact:true}).click();
      await page.waitForTimeout(300);
      const fullscreen=await page.evaluate(()=>Boolean(document.fullscreenElement));
      if(!fullscreen) throw Error('Fullscreen failed');
      await page.evaluate(()=>document.exitFullscreen());
      await page.emulateMedia({media:'print'});
      await page.waitForTimeout(300);
      const printed=await page.locator('.deck > .slide').evaluateAll(nodes=>nodes.every(n=>getComputedStyle(n).opacity==='1' && n.getBoundingClientRect().height===1080));
      if(!printed) consoleErrors.push('Print layout not fully visible: '+JSON.stringify(await page.locator('.deck > .slide').evaluateAll(nodes=>nodes.map(n=>({opacity:getComputedStyle(n).opacity,height:n.getBoundingClientRect().height})))));
      results.push({id:deck.id,pages:deck.pages,checks,consoleErrors,failedRequests,networkRequests,controls:{next:true,previous:true,notes:true,overview:true,presenterPreview:true,presenterSync:true,fullscreen,print:printed}});
      const thumbWidth=480,thumbHeight=270,gap=12,columns=4,rows=Math.ceil(deck.pages/columns);
      const images=[];
      for(let i=1;i<=deck.pages;i++) images.push({input:await sharp(path.join(qa,'screenshots',`${deck.id}-${String(i).padStart(2,'0')}.png`)).resize(thumbWidth,thumbHeight).toBuffer(),left:gap+((i-1)%columns)*(thumbWidth+gap),top:gap+Math.floor((i-1)/columns)*(thumbHeight+gap)});
      await sharp({create:{width:columns*(thumbWidth+gap)+gap,height:rows*(thumbHeight+gap)+gap,channels:3,background:'#dce4e9'}}).composite(images).jpeg({quality:88}).toFile(path.join(qa,`${deck.id}-contact.jpg`));
      await context.close();
      console.log(`${deck.id}: ${checks.length} layout checks; ${checks.reduce((n,c)=>n+c.errors.length,0)} issues`);
    }
    fs.writeFileSync(path.join(qa,'validation.json'),JSON.stringify({testedAt:new Date().toISOString(),browser:browser.version(),results},null,2));
    const bad=results.some(r=>r.consoleErrors.length || r.failedRequests.length || r.networkRequests.length || r.checks.some(c=>c.errors.length));
    if(bad) process.exitCode=1;
  } finally { await browser.close(); }
})().catch(e=>{console.error(e);process.exitCode=1;});
