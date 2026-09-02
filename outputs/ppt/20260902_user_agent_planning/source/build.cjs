// 仅生成本目录下的独立汇报材料，不读写应用代码、环境或原始规划文档。
const fs = require('node:fs');
const path = require('node:path');
const crypto = require('node:crypto');
const here = __dirname;
const output = path.dirname(here);
const read = name => fs.readFileSync(path.join(here, name), 'utf8');
const esc = text => String(text).replaceAll('&', '&amp;').replaceAll('<', '&lt;').replaceAll('>', '&gt;').replaceAll('"', '&quot;');
const icons = require('./icons.json');
const icon = name => `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${icons[name].map(([tag, attrs]) => `<${tag} ${Object.entries(attrs).map(([k,v]) => `${k}="${esc(v)}"`).join(' ')}></${tag}>`).join('')}</svg>`;
const bullets = items => `<ul class="bullets">${items.map(x=>`<li>${x}</li>`).join('')}</ul>`;
const takeaway = (text, caution=false) => `<div class="takeaway${caution?' caution':''}">${text}</div>`;
const flow = items => `<div class="flow">${items.map(([title,body],i)=>`${i?`<div class="arr">${icon('ArrowRight')}</div>`:''}<div class="node"><span class="num">0${i+1}</span><b>${title}</b><p>${body}</p></div>`).join('')}</div>`;
const cols = (items, kind='flat') => `<div class="grid g${items.length} fill">${items.map(([title,body],i)=>`<article class="${kind}${kind==='panel'&&i%2?' teal-panel':''}"><h3>${title}</h3>${Array.isArray(body)?bullets(body):`<p>${body}</p>`}</article>`).join('')}</div>`;
const table = (headers, rows, compact=false, widths=[]) => `<table class="matrix${compact?' compact':''}">${widths.length?`<colgroup>${widths.map(w=>`<col style="width:${w}%">`).join('')}</colgroup>`:''}<thead><tr>${headers.map(x=>`<th>${x}</th>`).join('')}</tr></thead><tbody>${rows.map(row=>`<tr>${row.map(x=>`<td>${x}</td>`).join('')}</tr>`).join('')}</tbody></table>`;
const comparison = (leftTitle,left,rightTitle,right) => `<div class="vs fill"><article class="side"><span class="eyebrow">当前常见做法</span><h3>${leftTitle}</h3>${bullets(left)}</article><div class="separator">${icon('ArrowRight')}</div><article class="side to"><span class="eyebrow">目标能力</span><h3>${rightTitle}</h3>${bullets(right)}</article></div>`;
const notes = (text,transition) => `<aside class="notes"><p>${text}</p><p>${transition}</p></aside>`;
const helpers = {icon,bullets,takeaway,flow,cols,table,comparison,notes};
const decks = [require('./planning.cjs')(helpers),require('./review.cjs')(helpers)];

// 从指定的完整模板替换内容区，沿用原运行时；主题内联，确保离线可用。
const template = read('vendor/presenter-template.html');
const head = template.slice(0, template.indexOf('<body'))
  .replace('<!DOCTYPE html>', '<!DOCTYPE html>\n<!--\n' + ['vendor/LICENSE-html-ppt.txt','vendor/LICENSE-lucide.txt'].map(read).join('\n').replaceAll('--', '- -') + '\n-->')
  .replace(/ data-themes="[^"]*"/, '')
  .replace(/<link[^>]+>\s*/g, '')
  .replace(/<title>.*?<\/title>/s, '<title>__TITLE__</title>');
let runtime = read('vendor/runtime.js');
// 保留页面布局类；缩略图必须和观众画布使用相同的内边距。
runtime = runtime.replace("clone.className = 'slide is-active';", "clone.className = s.className + ' is-active';")
  .replace("clone.style.padding = '72px 96px';", "clone.style.padding = '112px 104px 120px';")
  .replaceAll('letter-spacing: .15em;', 'letter-spacing: 0;');
const css = ['vendor/base.css','vendor/corporate-clean.css','vendor/presenter-template.css','deck.css'].map(read).join('\n');
const client = read('client.js');
const script = s => `<script>${s.replace(/<\/script/gi, '<\\/script')}</script>`;
const tools = [['ArrowLeft','上一页','ArrowLeft'],['ArrowRight','下一页','ArrowRight'],['LayoutGrid','页面总览','o'],['NotebookPen','讲稿','n'],['Presentation','演讲者视图','s'],['Maximize','全屏','f']];
const toolbar = `<nav class="toolbar" aria-label="演示控制">${tools.map(([i,title,key])=>`<button type="button" title="${title}" aria-label="${title}" data-key="${key}">${icon(i)}</button>`).join('')}</nav>`;
const manifest = [];
for (const deck of decks) {
  const pages = deck.slides.map((s,i)=>{
    const plainNotes = s.note.replace(/<[^>]*>/g,'');
    if (plainNotes.length < 150 || plainNotes.length > 330) throw Error(`${deck.id} page ${i+1}: notes length ${plainNotes.length}`);
    const content = s.cover ? `<div class="content">${s.body}</div>` : `<div class="page-heading"><p class="kicker">${s.kicker}</p><h2>${s.title}</h2><p class="subtitle">${s.subtitle}</p></div><div class="content">${s.body}</div>`;
    return `<section class="slide${s.cover?' cover':''}" data-title="${esc(s.title)}" data-source="${esc(s.source)}">
<header class="deck-header"><b>乘用车咨询 · 用户智能体</b><span>${deck.label} / 2026.09.02</span></header>
${content}<footer class="deck-footer"><span>${s.footer||'规划建议 · 需经真实项目验证，不代表已交付能力'}</span><span class="page-count">${String(i+1).padStart(2,'0')} / ${deck.slides.length}</span></footer>${s.note}</section>`;
  }).join('\n');
  const html = `${head.replace('__TITLE__',esc(deck.title)).replace('</head>',`<style>${css}</style></head>`)}
<body class="tpl-presenter-mode-reveal"><div class="deck">${pages}</div>${toolbar}
${script(runtime)}${script(client)}</body></html>`;
  fs.writeFileSync(path.join(output,deck.filename), html, 'utf8');
  manifest.push({id:deck.id,title:deck.title,file:deck.filename,pages:deck.slides.length,sha256:crypto.createHash('sha256').update(html).digest('hex'),slides:deck.slides.map((s,i)=>({page:i+1,title:s.title,source:s.source,notesChars:s.note.replace(/<[^>]*>/g,'').length}))});
}
fs.writeFileSync(path.join(output,'source-map.json'),JSON.stringify(manifest,null,2)+'\n','utf8');
console.log(JSON.stringify(manifest.map(({slides,...rest})=>rest),null,2));
