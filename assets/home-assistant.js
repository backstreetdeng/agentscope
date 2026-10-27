(function () {
  'use strict';
  if (document.getElementById('home-ai-launcher')) return;
  const style = document.createElement('link');
  style.rel = 'stylesheet'; style.href = '/assets/home-assistant.css';
  document.head.appendChild(style);
  const root = document.createElement('div');
  root.innerHTML = `
    <button id="home-ai-launcher" class="home-ai-launcher" type="button" aria-expanded="false" aria-controls="home-ai-panel"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" aria-hidden="true"><path d="M20 11.5a8 8 0 0 1-8 8H5l-3 2v-7a8 8 0 0 1 8-11h2a8 8 0 0 1 8 8Z"/><path d="M7 11h8m-8 4h5"/></svg><span>AI 问答</span></button>
    <section id="home-ai-panel" class="home-ai" role="dialog" aria-modal="false" aria-labelledby="home-ai-title" hidden>
      <header class="home-ai__head"><div><h2 id="home-ai-title">市场情报 AI 助手</h2><p class="home-ai__model">MiniMax · 政策 / 权益 / 新车 / 口碑</p></div><div class="home-ai__actions"><button type="button" class="home-ai__icon" data-action="new" aria-label="新建会话" title="新建会话">＋</button><button type="button" class="home-ai__icon" data-action="wide" aria-label="放大窗口" title="放大窗口">⛶</button><button type="button" class="home-ai__icon" data-action="close" aria-label="收起问答" title="收起问答">−</button></div></header>
      <div class="home-ai__messages" id="home-ai-messages" role="log" aria-live="polite" aria-relevant="additions text"></div>
      <form class="home-ai__composer"><textarea class="home-ai__input" aria-label="输入问题" maxlength="4000" placeholder="问一个市场问题，或继续追问…" rows="2"></textarea><div class="home-ai__send-row"><span class="home-ai__hint">Enter 发送 · Shift + Enter 换行</span><button type="submit" class="home-ai__send">发送</button></div><p class="home-ai__notice">AI 回答供参考，请结合来源与数据日期核对。</p></form>
    </section>`;
  document.body.appendChild(root);
  const launcher = root.querySelector('.home-ai-launcher');
  const panel = root.querySelector('.home-ai');
  const log = root.querySelector('.home-ai__messages');
  const input = root.querySelector('textarea');
  const send = root.querySelector('.home-ai__send');
  let messages = [], controller = null, timer = null, pending = false;
  function appendInline(parent, text) {
    const pieces = text.split(/(\*\*[^*]+\*\*|`[^`]+`)/g);
    pieces.forEach(piece => {
      if (piece.startsWith('**') && piece.endsWith('**')) { const strong = document.createElement('strong'); strong.textContent = piece.slice(2,-2); parent.appendChild(strong); }
      else if (piece.startsWith('`') && piece.endsWith('`')) { const code = document.createElement('code'); code.textContent = piece.slice(1,-1); parent.appendChild(code); }
      else parent.appendChild(document.createTextNode(piece));
    });
  }
  function renderAnswer(parent, text) {
    const lines = text.split('\n');
    for (let i = 0; i < lines.length; i++) {
      if (lines[i].includes('|') && /^\s*\|?\s*:?-{3,}/.test(lines[i+1] || '')) {
        const wrap = document.createElement('div'); wrap.className = 'home-ai__table'; const table = document.createElement('table');
        const cells = line => line.replace(/^\s*\|/, '').replace(/\|\s*$/, '').split('|');
        const header = document.createElement('tr'); cells(lines[i]).forEach(value => { const cell = document.createElement('th'); appendInline(cell, value.trim()); header.appendChild(cell); }); table.appendChild(header); i += 2;
        for (; i < lines.length && lines[i].includes('|'); i++) { const row = document.createElement('tr'); cells(lines[i]).forEach(value => { const cell = document.createElement('td'); appendInline(cell, value.trim()); row.appendChild(cell); }); table.appendChild(row); }
        i--; wrap.appendChild(table); parent.appendChild(wrap); continue;
      }
      const line = document.createElement('div');
      if (/^#{1,6}\s/.test(lines[i])) { const strong = document.createElement('strong'); appendInline(strong, lines[i].replace(/^#{1,6}\s+/, '')); line.appendChild(strong); }
      else appendInline(line, lines[i] || '\u00a0');
      parent.appendChild(line);
    }
  }
  function welcome() {
    log.replaceChildren();
    const content = document.createElement('div'); content.className = 'home-ai__welcome';
    content.innerHTML = '<h3>有什么可以帮你？</h3><p>快速查询市场情报，也可以就已有答案继续追问。</p><div class="home-ai__examples"></div>';
    ['上海有哪些购车补贴政策？', '理想i8有哪些官方权益？', '理想i8的口碑关注点是什么？'].forEach(question => {
      const button = document.createElement('button'); button.type = 'button'; button.className = 'home-ai__example'; button.textContent = question;
      button.addEventListener('click', () => { input.value = question; submit(); });
      content.querySelector('.home-ai__examples').appendChild(button);
    });
    log.appendChild(content);
  }
  function addMessage(role, text) {
    const item = document.createElement('article'); item.className = 'home-ai__message home-ai__message--' + role;
    const label = document.createElement('span'); label.className = 'home-ai__role'; label.textContent = role === 'user' ? '你' : role === 'error' ? '提示' : 'AI 助手';
    const content = document.createElement('div'); content.className = 'home-ai__text';
    if (role === 'assistant') renderAnswer(content, text); else content.textContent = text;
    item.append(label, content);
    if (role === 'assistant') {
      const copy = document.createElement('button'); copy.type = 'button'; copy.className = 'home-ai__copy'; copy.textContent = '复制回答';
      copy.addEventListener('click', async () => { try { await navigator.clipboard.writeText(text); copy.textContent = '已复制'; } catch (_) { copy.textContent = '请选中文字复制'; } });
      item.appendChild(copy);
    }
    log.appendChild(item); log.scrollTop = log.scrollHeight;
    return item;
  }
  function setPending(value) { pending = value; input.disabled = value; root.querySelector('[data-action="new"]').disabled = value; send.textContent = value ? '停止等待' : '发送'; send.disabled = !value && !input.value.trim(); panel.setAttribute('aria-busy', String(value)); }
  function open(value) { panel.hidden = !value; launcher.hidden = value; launcher.setAttribute('aria-expanded', String(value)); if (value) input.focus(); else launcher.focus(); }
  async function submit() {
    if (pending) { controller?.abort(); return; }
    const question = input.value.trim(); if (!question) return;
    if (messages.length >= 20) { addMessage('error', '这轮会话已达到 10 次问答，请点击右上角“＋”新建会话。'); return; }
    if (!messages.length) log.replaceChildren();
    messages.push({role:'user', content:question}); addMessage('user', question); input.value = '';
    controller = new AbortController(); const requestController = controller;
    const waiting = document.createElement('div'); waiting.className = 'home-ai__waiting'; waiting.textContent = '正在回答，查询数据可能需要一些时间…'; log.appendChild(waiting); log.scrollTop = log.scrollHeight;
    setPending(true); let timedOut = false;
    timer = setTimeout(() => { timedOut = true; requestController.abort(); }, 210000);
    try {
      const response = await fetch('/api/assistant/chat', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({messages}), signal:requestController.signal});
      if (response.status === 404) throw new Error('问答服务需要加载新版接口，请重启 7860 服务后再试。');
      const data = await response.json(); if (!response.ok || !data.answer) throw new Error(data.error || '暂未获得回答，请稍后重试。');
      messages.push({role:'assistant', content:data.answer}); addMessage('assistant', data.answer);
    } catch (error) {
      messages.pop(); input.value = question;
      addMessage('error', error.name === 'AbortError' ? (timedOut ? '等待超时，请稍后重试。' : '已停止等待；服务端可能仍在完成本次查询。可调整问题后重试。') : error.message);
    } finally { clearTimeout(timer); waiting.remove(); controller = null; setPending(false); input.focus(); log.scrollTop = log.scrollHeight; }
  }
  launcher.addEventListener('click', () => open(true));
  root.querySelector('form').addEventListener('submit', event => { event.preventDefault(); submit(); });
  input.addEventListener('input', () => { send.disabled = !input.value.trim(); });
  input.addEventListener('keydown', event => { if (event.key === 'Enter' && !event.shiftKey && !event.isComposing) { event.preventDefault(); submit(); } });
  panel.addEventListener('keydown', event => { if (event.key === 'Escape') open(false); });
  root.querySelector('[data-action="close"]').addEventListener('click', () => open(false));
  root.querySelector('[data-action="wide"]').addEventListener('click', event => { const wide = panel.classList.toggle('home-ai--wide'); event.currentTarget.setAttribute('aria-label', wide ? '还原窗口' : '放大窗口'); });
  root.querySelector('[data-action="new"]').addEventListener('click', () => { if (pending) return; messages = []; input.value = ''; welcome(); setPending(false); input.focus(); });
  welcome(); setPending(false);
})();
