(function () {
  'use strict';
  let loaded = false;
  let loading = false;
  const state = { mode: 'forecast', busy: false, runId: '', result: null, events: [] };
  const names = { total: '乘用车总量', bev: '纯电', phev: '插混 / 增程', hev: '普通混动', ice: '燃油' };
  const $ = (id) => document.getElementById(id);
  const text = (id, value) => { if ($(id)) $(id).textContent = value; };
  const esc = (s) => String(s).replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  const number = (n, digits = 0) => Number(n).toLocaleString('zh-CN', { maximumFractionDigits: digits, minimumFractionDigits: digits });

  async function request(url, options = {}, timeout = 20000) {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), timeout);
    try {
      const response = await fetch(url, { ...options, signal: controller.signal });
      const data = await response.json();
      if (!response.ok) throw new Error(data.error || '请求未完成，请重试。');
      return data;
    } finally { clearTimeout(timer); }
  }

  function setState(title, detail, error = false) {
    text('nf-state-text', title); text('nf-state-detail', detail);
    $('nf-state-dot').style.background = error ? '#d45a56' : state.busy ? '#5274ed' : '#2d9d8f';
  }

  function mode(modeName) {
    state.mode = modeName;
    document.querySelectorAll('[data-nf-mode]').forEach((button) => {
      const active = button.dataset.nfMode === modeName;
      button.classList.toggle('is-active', active); button.setAttribute('aria-selected', String(active));
    });
    const fields = { forecast: ['scenario'], scenario: ['event', 'mult'], indicator: ['powertrain', 'range'], explain: ['scenario', 'powertrain', 'month'] }[modeName];
    document.querySelectorAll('[data-nf-field]').forEach((field) => { field.hidden = !fields.includes(field.dataset.nfField); });
    text('nf-mode-description', { forecast: '选择一种情景，运行全国总量与动力结构预测。', scenario: '改变单项事件假设，与基准情景比较；其他假设保持一致。', indicator: '查询当前输入版本中的历史零售数据。', explain: '查看上一次预测任务的模型、数据截止和事件修正链。' }[modeName]);
    text('nf-run', { forecast: '运行预测 →', scenario: '重算这个假设 →', indicator: '查询指标 →', explain: '查看预测依据 →' }[modeName]);
  }

  function controls(disabled) {
    state.busy = disabled;
    document.querySelectorAll('#nf-form input,#nf-form select,#nf-form button,[data-nf-mode]').forEach((el) => { el.disabled = disabled; });
  }

  function render(job) {
    const data = job.data;
    state.result = job;
    if (['run_forecast', 'adjust_scenario'].includes(job.tool)) state.runId = job.run_id;
    $('nf-empty').hidden = true; $('nf-result-content').hidden = false; $('nf-download').disabled = false;
    text('nf-result-meta', `${({ base: '基准', bull: '乐观', bear: '保守' })[data.scenario] || data.scenario}情景 · 零售口径 · 数据截止 ${data.data_cutoff} · ${data.data_status === 'synthetic' ? '模拟数据' : '待业务验收'}`);
    $('nf-intervals').replaceChildren(); $('nf-metrics').replaceChildren();
    if (data.annual_by_powertrain) {
      const total = data.annual_by_powertrain.total;
      $('nf-metrics').innerHTML = `<div class="nf-metric"><p>2027 年零售总量 · P50</p><strong>${number(total.p50 / 10000, 2)}<small>万辆</small></strong><span>P10 ${number(total.p10 / 10000, 2)} — P90 ${number(total.p90 / 10000, 2)}</span></div><div class="nf-metric"><p>新能源渗透率 · P50</p><strong>${number(data.y2027_nev_penetration_pct, 1)}<small>%</small></strong><span>纯电与插混 / 增程合计</span></div>`;
      const max = Math.max(...Object.values(data.annual_by_powertrain).map((x) => x.p90), 1);
      $('nf-intervals').innerHTML = Object.entries(data.annual_by_powertrain).map(([key, value]) => {
        const position = (n) => 6 + 288 * n / max;
        return `<div class="nf-interval-row"><span>${esc(names[key])}</span><svg viewBox="0 0 300 18" role="img" aria-label="${esc(names[key])}预测区间"><line x1="6" x2="294" y1="9" y2="9" stroke="#edf1f8" stroke-width="3"/><line x1="${position(value.p10)}" x2="${position(value.p90)}" y1="9" y2="9" stroke="#ccd8fb" stroke-width="8" stroke-linecap="round"/><circle cx="${position(value.p50)}" cy="9" r="4" fill="#5274ed"/></svg><span>${number(value.p50 / 10000, 2)} 万辆</span></div>`;
      }).join('');
      $('nf-result-table').innerHTML = '<table><caption class="sr-only">2027 年各动力预测，单位万辆</caption><thead><tr><th>动力 · 万辆</th><th>P10</th><th>P50</th><th>P90</th></tr></thead><tbody>' + Object.entries(data.annual_by_powertrain).map(([key, value]) => `<tr><td>${esc(names[key])}</td><td>${number(value.p10 / 10000, 2)}</td><td>${number(value.p50 / 10000, 2)}</td><td>${number(value.p90 / 10000, 2)}</td></tr>`).join('') + '</tbody></table>';
      if (data.delta !== undefined) text('nf-result-meta', `${$('nf-result-meta').textContent} · 本项假设重算变化 ${data.delta >= 0 ? '+' : ''}${number(data.delta / 10000, 2)} 万辆`);
    } else if (data.data) {
      $('nf-result-table').innerHTML = '<table><thead><tr><th>月份</th><th>零售量 · 辆</th></tr></thead><tbody>' + Object.entries(data.data).map(([month, value]) => `<tr><td>${esc(month)}</td><td>${number(value)}</td></tr>`).join('') + '</tbody></table>';
    } else {
      $('nf-result-table').innerHTML = `<table><thead><tr><th>月份 / 动力</th><th>P10 · 辆</th><th>P50 · 辆</th><th>P90 · 辆</th></tr></thead><tbody><tr><td>${esc(data.ym)} / ${esc(names[data.powertrain])}</td><td>${number(data.p10)}</td><td>${number(data.p50)}</td><td>${number(data.p90)}</td></tr></tbody></table>`;
    }
    text('nf-evidence-text', `数据来源：${data.source}\n模型版本：${data.model_version}\n数据截止：${data.data_cutoff}\n输入版本：${data.input_sha256}\n任务：${job.run_id}\n年度区间方法：月度分位数加总，年度覆盖率尚未独立校准。\n事件修正链：\n${JSON.stringify(data.adjustment_chain || [], null, 2)}`);
  }

  async function run(event) {
    event.preventDefault(); if (state.busy) return;
    const selected = state.mode;
    if (selected === 'explain' && !state.runId) { setState('请先运行预测', '依据追溯需要本轮已完成的预测任务。', true); return; }
    let tool, args;
    if (selected === 'forecast') { tool = 'run_forecast'; args = { scenario: $('nf-scenario').value }; }
    else if (selected === 'scenario') { tool = 'adjust_scenario'; args = { event_id: $('nf-event').value, mult: Number($('nf-mult').value) }; }
    else if (selected === 'indicator') { tool = 'query_indicator'; args = { powertrain: $('nf-powertrain').value, start: $('nf-start').value, end: $('nf-end').value }; }
    else { tool = 'explain_forecast'; args = { ym: $('nf-month').value, powertrain: $('nf-powertrain').value, scenario: $('nf-scenario').value }; }
    controls(true); setState('正在提交', '只调用数学引擎，不调用大模型。');
    try {
      let job = await request('/api/forecast-engine/jobs', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ tool, arguments: args, run_id: selected === 'explain' ? state.runId : '' }) });
      const started = Date.now();
      while (job.status === 'running') {
        setState('数学引擎计算中', `已用时 ${Math.floor((Date.now() - started) / 1000)} 秒；任务状态来自后端。`);
        if (Date.now() - started > 190000) throw new Error('等待结果超时，后台回执已保留。');
        await new Promise((resolve) => setTimeout(resolve, 1200));
        job = await request('/api/forecast-engine/jobs?run_id=' + encodeURIComponent(job.run_id));
      }
      if (job.status !== 'completed') throw new Error(job.message || '预测没有完成。');
      render(job); setState('结果已生成', '数据版本、情景和计算回执已保存；当前仅供内部核验。');
    } catch (error) { setState('本次操作未完成', error.message, true); }
    finally { controls(false); }
  }

  async function chat(event) {
    event.preventDefault(); const question = $('nf-question').value.trim(); if (!question) return;
    $('nf-chat-submit').disabled = true; $('nf-chat-answer').hidden = false; text('nf-chat-answer', '助手正在根据问题选择预测工具；所有预测数值仍由数学引擎计算。');
    try {
      const result = await request('/api/chat', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ agent: 'market_strategy', analysis_type: 'forecast_engine', model_provider: $('nf-model').value, question }) }, 190000);
      text('nf-chat-answer', result.answer || '本轮没有可展示的解释，请查看工具执行状态。');
    } catch (error) { text('nf-chat-answer', '本次分析未完成：' + error.message); }
    finally { $('nf-chat-submit').disabled = false; }
  }

  async function load() {
    if (loaded || loading) return; loading = true;
    const root = $('forecast-engine-mount');
    try {
      const response = await fetch('/forecast-engine-view'); if (!response.ok) throw new Error('新版工作区加载失败。');
      root.innerHTML = await response.text();
      document.querySelectorAll('[data-nf-mode]').forEach((el) => el.addEventListener('click', () => mode(el.dataset.nfMode)));
      $('nf-form').addEventListener('submit', run); $('nf-chat-form').addEventListener('submit', chat);
      $('nf-event').addEventListener('change', () => { const event = state.events.find((item) => item.event_id === $('nf-event').value); if (event) $('nf-mult').value = event.mult_base; });
      $('nf-download').addEventListener('click', () => { if (!state.result) return; const url = URL.createObjectURL(new Blob([JSON.stringify(state.result, null, 2)], { type: 'application/json' })); const link = document.createElement('a'); link.href = url; link.download = '新版市场预测-内部核验-' + state.result.run_id + '.json'; link.click(); setTimeout(() => URL.revokeObjectURL(url), 1000); });
      const data = await request('/api/forecast-engine/status'); state.events = data.events;
      text('nf-engine-status', '数学引擎已就绪'); text('nf-data-label', data.data_status === 'synthetic' ? '模拟占位数据 · 等待真实数据接入' : '真实数据 · 业务验收待完成');
      text('nf-data-period', `${data.first_month} — ${data.data_cutoff}`); text('nf-history-count', `${data.months} 个月`); text('nf-cutoff', data.data_cutoff); $('nf-end').value = data.data_cutoff;
      $('nf-event').innerHTML = data.events.map((item) => `<option value="${esc(item.event_id)}">${esc(item.label)}</option>`).join('');
      if (data.events[0]) $('nf-mult').value = data.events[0].mult_base;
      loaded = true;
    } catch (error) { root.textContent = error.message + ' 请刷新页面重试。'; }
    finally { loading = false; }
  }
  document.addEventListener('view:enter', (event) => { if (event.detail.view === 'forecast-engine') load(); });
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', () => { if (location.hash === '#forecast-engine') load(); });
  else if (location.hash === '#forecast-engine') load();
}());
