(function () {
  'use strict';
  let loaded = false;
  let loading = false;
  const state = { mode: 'chronos', busy: false, runId: '', result: null, events: [], chronos: null, sarimax: null, engine: null, chronosRuns: {}, modelRuns: { forecast: {}, backtest: {} }, priorQuestions: [] };
  const storageKey = 'forecast-engine-model-runs-v1';
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

  function clearAssistant() {
    state.priorQuestions = [];
    if ($('nf-chat-answer')) { $('nf-chat-answer').replaceChildren(); $('nf-chat-answer').hidden = true; }
    text('nf-chat-context', '请先运行销量预测或历史回测，再向助手提问。');
  }

  function matchingRun(job, operation) {
    if (!job || job.status !== 'completed' || job.operation !== operation || !job.data) return false;
    const data = job.data;
    return data.province === $('nf-chronos-region').value && data.energy === $('nf-chronos-energy').value &&
      data.data_cutoff === $('nf-chronos-cutoff').value && data.source_sha256 === state.chronos?.source_sha256 &&
      (operation !== 'forecast' || (Array.isArray(data.forecast) && data.forecast.length === Number($('nf-chronos-horizon').value)));
  }

  function refreshCompareHint() {
    const operation = state.mode === 'chronos-backtest' ? 'backtest' : 'forecast';
    const available = state.mode.startsWith('chronos') && $('nf-forecast-model').value !== 'oil';
    $('nf-compare').hidden = !available; $('nf-compare-hint').hidden = !available;
    if (!available) return;
    const label = operation === 'forecast' ? '预测' : '回测';
    text('nf-compare', `比较两个模型的${label} →`);
    const runs = state.modelRuns[operation];
    const missing = [['chronos','Chronos-2'],['sarimax','SARIMAX']].filter(([key]) => !matchingRun(runs[key], operation)).map(([,label]) => label);
    text('nf-compare-hint', missing.length ? `当前条件下还需运行：${missing.join('、')}。` : `两个模型的${label}已就绪，可以比较。`);
  }

  function rememberRun(job, operation, model) {
    state.modelRuns[operation][model] = job;
    try {
      const ids = {};
      for (const op of ['forecast','backtest']) {
        ids[op] = {};
        for (const key of ['chronos','sarimax','oil']) if (state.modelRuns[op][key]) ids[op][key] = state.modelRuns[op][key].run_id;
      }
      localStorage.setItem(storageKey, JSON.stringify({ ids, last: { operation, model } }));
    } catch (_) { /* Storage may be unavailable; current page can still compare. */ }
    refreshCompareHint();
  }

  async function restoreRuns() {
    let saved;
    try { saved = JSON.parse(localStorage.getItem(storageKey) || 'null'); } catch (_) { return; }
    if (!saved || !saved.ids || !saved.last) return;
    for (const op of ['forecast','backtest']) for (const key of ['chronos','sarimax','oil']) {
      const id = saved.ids[op]?.[key];
      const endpointKey = key === 'oil' ? 'sarimax' : key;
      if (typeof id !== 'string' || !new RegExp(`^${endpointKey}-[a-f0-9]{32}$`).test(id)) continue;
      try {
        const job = await request(`/api/forecast-engine/${endpointKey}-jobs?run_id=${encodeURIComponent(id)}`);
        if (job.status === 'completed' && job.operation === op && job.data) state.modelRuns[op][key] = job;
      } catch (_) { /* Missing receipts do not block a new run. */ }
    }
    const { operation, model } = saved.last;
    const job = state.modelRuns[operation]?.[model];
    if (!job || !job.data || job.data.source_sha256 !== state.chronos?.source_sha256) return;
    const data = job.data;
    if (![...$('nf-chronos-region').options].some((o) => o.value === data.province) || ![...$('nf-chronos-energy').options].some((o) => o.value === data.energy)) return;
    $('nf-chronos-region').value = data.province; $('nf-chronos-energy').value = data.energy; $('nf-chronos-cutoff').value = data.data_cutoff;
    if (operation === 'forecast' && Array.isArray(data.forecast)) $('nf-chronos-horizon').value = data.forecast.length;
    $('nf-forecast-model').value = model;
    $('nf-forecast-model').dispatchEvent(new Event('change'));
    mode(operation === 'backtest' ? 'chronos-backtest' : 'chronos');
    if (matchingRun(job, operation)) { renderChronos(job); setState('已恢复上次结果', '已从本机任务回执恢复，可继续比较。'); }
  }

  function mode(modeName) {
    if (state.mode !== modeName) {
      state.result = null;
      $('nf-empty').hidden = false; $('nf-result-content').hidden = true; $('nf-download').disabled = true;
      setState('等待运行', '已切换操作，请运行以获取对应结果。');
      clearAssistant();
    }
    state.mode = modeName;
    document.querySelectorAll('[data-nf-mode]').forEach((button) => {
      const active = button.dataset.nfMode === modeName;
      button.classList.toggle('is-active', active); button.setAttribute('aria-selected', String(active));
    });
    const fields = { chronos: ['chronos-model', 'chronos-region', 'chronos-energy', 'chronos-cutoff', 'chronos-horizon'], 'chronos-backtest': ['chronos-model', 'chronos-region', 'chronos-energy', 'chronos-cutoff'], forecast: ['scenario'], scenario: ['event', 'mult'], indicator: ['powertrain', 'range'], explain: ['scenario', 'powertrain', 'month'] }[modeName];
    document.querySelectorAll('[data-nf-field]').forEach((field) => { field.hidden = !fields.includes(field.dataset.nfField); });
    text('nf-mode-description', { chronos: '选择范围，用历史零售数据生成未来月度预测区间。', 'chronos-backtest': '使用滚动历史切分，检查预测误差与月度区间覆盖。', forecast: '选择一种情景，运行引擎的总量与动力结构预测。', scenario: '改变单项事件假设，与基准情景比较；其他假设保持一致。', indicator: '查询当前输入版本中的历史零售数据。', explain: '查看上一次预测任务的模型、数据截止和事件修正链。' }[modeName]);
    text('nf-run', { chronos: '运行预测 →', 'chronos-backtest': '运行历史回测 →', forecast: '运行预测 →', scenario: '重算这个假设 →', indicator: '查询指标 →', explain: '查看预测依据 →' }[modeName]);
    $('nf-comparison').hidden = true; $('nf-comparison').replaceChildren();
    refreshCompareHint();
    const current = modeName.startsWith('chronos') ? state.chronos : state.engine;
    if (current) {
      text('nf-cutoff', current.last_month || current.data_cutoff);
      text('nf-history-count', modeName.startsWith('chronos') ? '依选择范围计算' : `${current.months} 个月`);
    }
    if (modeName.startsWith('chronos')) {
      const operation = modeName === 'chronos-backtest' ? 'backtest' : 'forecast';
      const saved = state.modelRuns[operation][$('nf-forecast-model').value];
      if (matchingRun(saved, operation)) { renderChronos(saved); setState('已恢复模型结果', '当前条件下的结果已从本机记录恢复。'); }
    }
  }

  function controls(disabled) {
    state.busy = disabled;
    document.querySelectorAll('#nf-form input,#nf-form select,#nf-form button,[data-nf-mode]').forEach((el) => { el.disabled = disabled; });
    $('nf-compare').disabled = disabled;
  }

  function render(job) {
    const data = job.data;
    state.result = job;
    clearAssistant();
    if (['run_forecast', 'adjust_scenario'].includes(job.tool)) state.runId = job.run_id;
    $('nf-empty').hidden = true; $('nf-result-content').hidden = false; $('nf-download').disabled = false;
    $('nf-decision').hidden = true;
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

  function renderChronos(job) {
    const data = job.data; state.result = job;
    clearAssistant();
    const operation = data.forecast ? 'forecast' : 'backtest';
    const isSarimax = job.run_id.startsWith('sarimax-');
    if (!isSarimax) state.chronosRuns[operation] = job;
    rememberRun(job, operation, data.profile === 'gd_oil' ? 'oil' : isSarimax ? 'sarimax' : 'chronos');
    text('nf-chat-context', isSarimax ? 'SARIMAX 结果暂未接入预测助手；切换 Chronos-2 可使用本机问答。' : `已关联${operation === 'forecast' ? '销量预测' : '历史回测'}：${data.province} / ${data.energy}，截止 ${data.data_cutoff}。`);
    $('nf-empty').hidden = true; $('nf-result-content').hidden = false; $('nf-download').disabled = false;
    $('nf-decision').hidden = false; text('nf-decision', `决策含义：${data.decision_meaning}`);
    text('nf-result-meta', `${data.model} · ${data.province} · ${data.energy} · 零售 · ${data.scenario} · 数据截止 ${data.data_cutoff} · 真实数据待验收`);
    $('nf-intervals').replaceChildren(); $('nf-metrics').replaceChildren();
    if (data.forecast) {
      const first = data.forecast[0];
      $('nf-metrics').innerHTML = `<div class="nf-metric"><p>${esc(first.month)} ${isSarimax ? '预测均值' : '预测 · P50'}</p><strong>${number(first.p50)}<small>辆</small></strong><span>${isSarimax ? '条件区间' : 'P10–P90'} ${number(first.p10)} — ${number(first.p90)} 辆</span></div><div class="nf-metric"><p>历史数据</p><strong>${data.history_months}<small>个月</small></strong><span>${esc(data.history_start)} — ${esc(data.data_cutoff)}</span></div>`;
      if (data.forecast.length > 1) {
        const rows = data.forecast, max = Math.max(...rows.map((r) => r.p90), 1), x = (i) => 24 + i * 552 / (rows.length - 1), y = (v) => 140 - 120 * v / max;
        const upper = rows.map((r, i) => `${x(i)},${y(r.p90)}`).join(' '), lower = rows.map((r, i) => `${x(i)},${y(r.p10)}`).reverse().join(' '), middle = rows.map((r, i) => `${x(i)},${y(r.p50)}`).join(' ');
        $('nf-intervals').innerHTML = `<p class="nf-chart-title">月度预测区间 <span>${isSarimax ? '蓝线预测均值 · 条件 80% 区间' : '蓝线 P50 · 浅色范围 P10–P90'}</span></p><svg class="nf-chronos-chart" viewBox="0 0 600 160" role="img" aria-label="月度预测及区间，详细数值见下表"><line x1="24" y1="140" x2="576" y2="140" stroke="#e2e8f3"/><polygon points="${upper} ${lower}" fill="#dce6ff"/><polyline points="${middle}" fill="none" stroke="#5274ed" stroke-width="3" vector-effect="non-scaling-stroke"/></svg><div class="nf-chart-axis"><span>${esc(rows[0].month)}</span><span>${esc(rows[rows.length-1].month)}</span></div>`;
      }
      $('nf-result-table').innerHTML = '<table><thead><tr><th>预测月</th><th>' + (isSarimax ? '区间下界' : 'P10') + ' · 辆</th><th>' + (isSarimax ? '预测均值' : 'P50') + ' · 辆</th><th>' + (isSarimax ? '区间上界' : 'P90') + ' · 辆</th></tr></thead><tbody>' + data.forecast.map((row) => `<tr><td>${esc(row.month)}</td><td>${number(row.p10)}</td><td>${number(row.p50)}</td><td>${number(row.p90)}</td></tr>`).join('') + '</tbody></table>';
    } else {
      const b = data.backtest;
      const mape = b.mape_pct === null ? '无法计算' : number(b.mape_pct, 2) + '%';
      const ref = b.reference_1_6;
      if (!isSarimax && data.province === '31省份合计' && data.energy === '四类合计（不含燃料电池）' && (ref.mape_pct === null || ref.mape_pct > 10 || ref.interval_coverage_pct < 70 || ref.interval_coverage_pct > 90)) {
        text('nf-decision', '1–6 个月回测尚未达到迁移文档总量参考门槛（MAPE ≤ 10%，覆盖率 70%–90%）；四类合计不含燃料电池，口径不完全相同，仅作内部比较。');
      } else {
        text('nf-decision', '本次回测仅供内部核验；是否满足业务精度及发布要求仍需完整评审。');
      }
      $('nf-metrics').innerHTML = `<div class="nf-metric"><p>1–12 个月 MAPE · 内部核验</p><strong>${esc(mape)}</strong><span>正实际值样本 ${b.mape_eligible}；零值排除 ${b.zero_actual_excluded}</span></div><div class="nf-metric"><p>${isSarimax ? '条件区间覆盖率' : '月度 P10–P90 覆盖率'}</p><strong>${number(b.interval_coverage_pct, 1)}<small>%</small></strong><span>${b.origins} 个起点 · ${b.observations} 个预测点</span></div>`;
      const pct = (x) => x === null ? '无法计算' : number(x, 2) + '%';
      $('nf-result-table').innerHTML = '<p class="nf-hint">' + esc(b.note) + '</p><table><thead><tr><th>预测期</th><th>MAE · 辆</th><th>模型 WAPE</th><th>季节基线 WAPE</th><th>区间覆盖</th></tr></thead><tbody>' + Object.entries(b.by_horizon).map(([h, x]) => `<tr><td>${esc(h)} 个月</td><td>${number(x.mae)}</td><td>${pct(x.wape_pct)}</td><td>${pct(x.seasonal_naive_wape_pct)}</td><td>${pct(x.interval_coverage_pct)}</td></tr>`).join('') + '</tbody></table><details class="nf-evidence"><summary>查看各起点明细</summary><table><thead><tr><th>起点</th><th>目标月</th><th>实际 · 辆</th><th>' + (isSarimax ? '区间下界' : 'P10') + '</th><th>' + (isSarimax ? '预测均值' : 'P50') + '</th><th>' + (isSarimax ? '区间上界' : 'P90') + '</th></tr></thead><tbody>' + b.records.map((r) => `<tr><td>${esc(r.origin)}</td><td>${esc(r.month)}</td><td>${number(r.actual)}</td><td>${number(r.p10)}</td><td>${number(r.p50)}</td><td>${number(r.p90)}</td></tr>`).join('') + '</tbody></table></details>';
    }
    if (data.benchmark) {
      const labels = {oil_lag1:'油价滞后1月（主试验）',oil_lag3:'油价滞后3月（敏感性）',sarimax:data.model_revision.startsWith('log-constrained-') ? 'SARIMAX对数基线（无变量）' : 'SARIMAX线性基线（旧版）',chronos:'Chronos-2'};
      const pct = (v) => v === null ? '无法计算' : number(v,2)+'%';
      const failures = document.createElement('p'); failures.className = 'nf-hint';
      failures.textContent = (data.stability_passed ? '12个起点数值检查全部成功，业务精度未通过。' : `稳定性未通过：${data.failures.length} 次模型/起点失败；下表仅比较共同成功起点，不代表完整回测通过。`) + (data.recommendation || '');
      $('nf-result-table').appendChild(failures);
      $('nf-result-table').innerHTML += '<h3>共同窗口模型比较</h3><p>各模型历史从2020-04开始，使用相同起点；不按本次回测自动选模型。</p><table><thead><tr><th>模型</th><th>预测期</th><th>样本数</th><th>MAE · 辆</th><th>WAPE</th><th>条件/分位区间覆盖</th><th>季节基线WAPE</th></tr></thead><tbody>' + Object.entries(data.benchmark).flatMap(([key,value]) => Object.entries(value.by_horizon).map(([h,row]) => `<tr><td>${esc(labels[key])}</td><td>${esc(h)}月</td><td>${number(row.observations)}</td><td>${number(row.mae)}</td><td>${pct(row.wape_pct)}</td><td>${pct(row.interval_coverage_pct)}</td><td>${pct(row.seasonal_naive_wape_pct)}</td></tr>`)).join('') + '</tbody></table><details><summary>查看失败起点和原因</summary><pre>' + esc(JSON.stringify(data.failures,null,2)) + '</pre></details>';
    }
    text('nf-evidence-text', `来源：${data.source}\n输入 SHA256：${data.source_sha256}\n模型：${data.model}（${data.model_revision}）\n方法：${data.method}\n后处理：${data.postprocessing}\n历史：${data.history_start} — ${data.data_cutoff}\n缺项处理：${data.missing_combination}\n决策含义：${data.decision_meaning}\n任务：${job.run_id}` + (data.profile === 'gd_oil' ? '\n油价假设：' + JSON.stringify(data.assumptions || {}) + '\n油价文件指纹：' + JSON.stringify(data.oil_hashes) + '\n限制：' + data.limitations.join('；') : ''));
  }

  async function run(event) {
    event.preventDefault(); if (state.busy) return;
    const selected = state.mode;
    if (selected.startsWith('chronos')) {
      const selectedModel = $('nf-forecast-model').value;
      const currentModel = selectedModel !== 'chronos' ? state.sarimax : state.chronos;
      if (!currentModel || !currentModel.model_available) { setState('模型或数据不可用', '检查本地模型依赖与历史数据后重试。', true); return; }
      state.result = null; clearAssistant(); $('nf-comparison').hidden = true; $('nf-comparison').replaceChildren();
      $('nf-empty').hidden = false; $('nf-result-content').hidden = true; $('nf-download').disabled = true;
      controls(true); setState('正在提交', '使用本地预测模型，不调用大语言模型。');
      try {
        const endpoint = selectedModel !== 'chronos' ? '/api/forecast-engine/sarimax-jobs' : '/api/forecast-engine/chronos-jobs';
        let job = await request(endpoint, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ operation: selected === 'chronos' ? 'forecast' : 'backtest', province: $('nf-chronos-region').value, energy: $('nf-chronos-energy').value, cutoff: $('nf-chronos-cutoff').value, horizon: Number($('nf-chronos-horizon').value), ...(selectedModel === 'oil' ? {profile:'gd_oil'} : {}) }) });
        const started = Date.now();
        while (job.status === 'running') {
          setState('模型计算中', `已用时 ${Math.floor((Date.now() - started) / 1000)} 秒。`);
          if (Date.now() - started > 600000) throw new Error('等待超时，请稍后查看本地计算回执。');
          await new Promise((resolve) => setTimeout(resolve, 1200));
          job = await request(endpoint + '?run_id=' + encodeURIComponent(job.run_id));
        }
        if (job.status !== 'completed') throw new Error(job.message || '计算没有完成。');
        renderChronos(job); setState('结果已生成', '预测及回测仅供内部核验；数据和任务回执已保留。');
      } catch (error) { setState('本次操作未完成', error.message, true); }
      finally { controls(false); }
      return;
    }
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
    const job = state.result;
    if (!job || !/^chronos-[a-f0-9]{32}$/.test(job.run_id || '') || job.status !== 'completed') {
      $('nf-chat-answer').hidden = false; text('nf-chat-answer', job && /^sarimax-/.test(job.run_id || '') ? 'SARIMAX 尚未接入预测助手，请切换 Chronos-2。' : '请先运行销量预测或历史回测，再基于该结果提问。'); return;
    }
    const operation = job.data.forecast ? 'forecast' : 'backtest';
    const other = state.chronosRuns[operation === 'forecast' ? 'backtest' : 'forecast'];
    const keys = ['source_sha256','data_cutoff','province','energy','model','scenario'];
    const related = other && keys.every((key) => other.data[key] === job.data[key]) ? other.run_id : '';
    const runId = job.run_id;
    $('nf-chat-submit').disabled = true; $('nf-chat-answer').hidden = false;
    const loading = document.createElement('p'); loading.textContent = '正在本机分析当前任务的数据…'; $('nf-chat-answer').appendChild(loading);
    try {
      const result = await request('/api/forecast-engine/local-insights', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ run_id: runId, related_run_id: related, question, prior_questions: state.priorQuestions.slice(-6) }) }, 60000);
      if (!state.result || state.result.run_id !== runId) return;
      loading.remove();
      const entry = document.createElement('div'); entry.className = 'nf-chat-entry';
      const prompt = document.createElement('strong'); prompt.textContent = '您：' + question; entry.appendChild(prompt);
      const list = document.createElement('ul');
      result.facts.forEach((fact) => { const item = document.createElement('li'); item.textContent = fact; list.appendChild(item); });
      entry.appendChild(list);
      const note = document.createElement('p'); note.className = 'nf-hint'; note.textContent = result.message; entry.appendChild(note);
      $('nf-chat-answer').appendChild(entry); state.priorQuestions.push(question); state.priorQuestions = state.priorQuestions.slice(-6); $('nf-question').value = '';
    } catch (error) { loading.textContent = '本次分析未完成：' + error.message; }
    finally { $('nf-chat-submit').disabled = false; }
  }

  async function deepseekAnalysis() {
    const job = state.result;
    if (!job || job.status !== 'completed' || !job.data || !job.data.forecast || !/^chronos-[a-f0-9]{32}$/.test(job.run_id || '')) {
      $('nf-chat-answer').hidden = false;
      text('nf-chat-answer', '请先运行未来销量预测；历史回测不能发送给 DeepSeek。');
      return;
    }
    const runId = job.run_id;
    $('nf-ai-submit').disabled = true;
    $('nf-chat-answer').hidden = false;
    const loading = document.createElement('p');
    loading.textContent = '正在通过预测信息质量门并调用 DeepSeek…';
    $('nf-chat-answer').appendChild(loading);
    try {
      const result = await request('/api/forecast-engine/deepseek-insights', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ run_id: runId, intent: $('nf-ai-intent').value, model: $('nf-ai-model').value })
      }, 75000);
      if (!state.result || state.result.run_id !== runId) return;
      loading.remove();
      const entry = document.createElement('div'); entry.className = 'nf-chat-entry';
      const title = document.createElement('strong'); title.textContent = result.model + ' · 预测业务分析'; entry.appendChild(title);
      const analysis = document.createElement('p'); analysis.textContent = result.analysis; analysis.style.whiteSpace = 'pre-wrap'; entry.appendChild(analysis);
      const note = document.createElement('p'); note.className = 'nf-hint'; note.textContent = result.message + ' 分析仅供内部核验，不能替代业务验收。'; entry.appendChild(note);
      $('nf-chat-answer').appendChild(entry);
    } catch (error) { loading.textContent = 'DeepSeek 分析未完成：' + error.message; }
    finally { $('nf-ai-submit').disabled = false; }
  }

  async function compareModels() {
    const operation = state.mode === 'chronos-backtest' ? 'backtest' : 'forecast';
    const chronos = state.modelRuns[operation].chronos, sarimax = state.modelRuns[operation].sarimax;
    const target = $('nf-comparison'); target.hidden = false;
    if (![chronos, sarimax].every((job) => matchingRun(job, operation))) {
      target.textContent = `请按当前条件分别运行两种模型的${operation === 'forecast' ? '销量预测' : '历史回测'}。`; return;
    }
    const c = chronos.data, s = sarimax.data;
    const keys = ['source_sha256','data_cutoff','history_start','province','energy','metric','unit'];
    if (keys.some((key) => !c[key] || c[key] !== s[key])) {
      target.textContent = '两个结果的数据版本或统计范围不同，请按相同条件重新运行。'; return;
    }
    if (operation === 'forecast') {
      const cr = c.forecast, sr = s.forecast;
      if (!Array.isArray(cr) || !Array.isArray(sr) || !cr.length || cr.length !== sr.length || cr.some((row,i) => row.month !== sr[i]?.month || ![row.p10,row.p50,row.p90,sr[i].p10,sr[i].p50,sr[i].p90].every(Number.isFinite))) {
        target.textContent = '两个预测的月份或结果不一致，请重新运行。'; return;
      }
      target.innerHTML = '<h3>同条件销量预测比较</h3><p class="nf-hint">同一地区、动力类型、数据版本、截止月和预测月数。Chronos-2 是预测中位数，SARIMAX 是预测均值；两者的预测范围采用不同方法，不能直接视为同等准确。</p><table><thead><tr><th>预测月</th><th>Chronos-2 中位数 · 辆</th><th>Chronos-2 预测范围 · 辆</th><th>SARIMAX 均值 · 辆</th><th>SARIMAX 预测范围 · 辆</th></tr></thead><tbody>' + cr.map((row,i) => `<tr><td>${esc(row.month)}</td><td>${number(row.p50)}</td><td>${number(row.p10)} — ${number(row.p90)}</td><td>${number(sr[i].p50)}</td><td>${number(sr[i].p10)} — ${number(sr[i].p90)}</td></tr>`).join('') + '</tbody></table>';
      return;
    }
    target.textContent = '正在核对回测范围与起点…';
    try {
      const result = await request('/api/forecast-engine/model-comparison', { method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({chronos_run_id:chronos.run_id,sarimax_run_id:sarimax.run_id}) });
      if (state.modelRuns.backtest.chronos !== chronos || state.modelRuns.backtest.sarimax !== sarimax || state.mode !== 'chronos-backtest' || !matchingRun(chronos, operation) || !matchingRun(sarimax, operation)) return;
      const pct = (value) => value === null ? '无法计算' : number(value, 2) + '%';
      target.innerHTML = '<h3>同口径回测比较</h3><p class="nf-hint">' + esc(result.note) + '</p><table><thead><tr><th>预测期</th><th>样本数</th><th>Chronos MAE · 辆</th><th>SARIMAX MAE · 辆</th><th>季节基线 MAE · 辆</th><th>Chronos WAPE</th><th>SARIMAX WAPE</th><th>季节基线 WAPE</th><th>Chronos 覆盖率</th><th>SARIMAX 覆盖率</th></tr></thead><tbody>' + result.rows.map((row) => `<tr><td>${number(row.horizon)} 个月</td><td>${number(row.observations)}</td><td>${number(row.chronos.mae)}</td><td>${number(row.sarimax.mae)}</td><td>${number(row.seasonal_naive_mae)}</td><td>${pct(row.chronos.wape_pct)}</td><td>${pct(row.sarimax.wape_pct)}</td><td>${pct(row.seasonal_naive_wape_pct)}</td><td>${pct(row.chronos.interval_coverage_pct)}</td><td>${pct(row.sarimax.interval_coverage_pct)}</td></tr>`).join('') + '</tbody></table>';
    } catch (error) { target.textContent = '无法比较：' + error.message; }
  }

  async function load() {
    if (loaded || loading) return; loading = true;
    const root = $('forecast-engine-mount');
    try {
      const response = await fetch('/forecast-engine-view'); if (!response.ok) throw new Error('新版工作区加载失败。');
      root.innerHTML = await response.text();
      document.querySelectorAll('[data-nf-mode]').forEach((el) => el.addEventListener('click', () => mode(el.dataset.nfMode)));
      $('nf-form').addEventListener('submit', run); $('nf-chat-form').addEventListener('submit', chat);
      $('nf-ai-submit').addEventListener('click', deepseekAnalysis);
      $('nf-compare').addEventListener('click', compareModels);
      $('nf-forecast-model').addEventListener('change', () => {
        state.result = null; $('nf-empty').hidden = false; $('nf-result-content').hidden = true; $('nf-download').disabled = true;
        clearAssistant();
        text('nf-model-hint', $('nf-forecast-model').value === 'oil' ? '仅广东插混（含增程），最多12月。使用92号月均油价，固定滞后1月，未来油价保持最近水平；当前快照内部试验，非因果。回测同时计算共同窗口模型比较。' : $('nf-forecast-model').value === 'sarimax' ? '根据历史销量的趋势和季节变化预测未来销量，可与 Chronos-2 对比参考；暂未考虑价格、优惠和油价等因素。' : '根据历史销量走势预测未来销量，并给出可能范围，帮助您提前规划。');
        text('nf-interval-label', $('nf-forecast-model').value !== 'chronos' ? '条件 80% 区间 / 均值' : 'P10 / P50 / P90');
        const operation = state.mode === 'chronos-backtest' ? 'backtest' : 'forecast';
        const saved = state.modelRuns[operation][$('nf-forecast-model').value];
        if (state.mode.startsWith('chronos') && matchingRun(saved, operation)) { renderChronos(saved); setState('已恢复模型结果', '当前条件下的结果已从本机记录恢复。'); }
        else setState('模型已更改', '请运行当前条件下的预测或历史回测。');
        refreshCompareHint();
      });
      ['nf-chronos-region', 'nf-chronos-energy', 'nf-chronos-cutoff', 'nf-chronos-horizon'].forEach((id) => {
        $(id).addEventListener('change', () => {
          $('nf-comparison').hidden = true; $('nf-comparison').replaceChildren(); refreshCompareHint();
          if (!state.mode.startsWith('chronos') || !state.result) return;
          state.result = null; $('nf-empty').hidden = false; $('nf-result-content').hidden = true; $('nf-download').disabled = true;
          clearAssistant();
          setState('条件已更改', '请重新运行，避免把上一次结果当作新条件的预测。');
        });
      });
      $('nf-event').addEventListener('change', () => { const event = state.events.find((item) => item.event_id === $('nf-event').value); if (event) $('nf-mult').value = event.mult_base; });
      $('nf-download').addEventListener('click', () => { if (!state.result) return; const url = URL.createObjectURL(new Blob([JSON.stringify(state.result, null, 2)], { type: 'application/json' })); const link = document.createElement('a'); link.href = url; link.download = '新版市场预测-内部核验-' + state.result.run_id + '.json'; link.click(); setTimeout(() => URL.revokeObjectURL(url), 1000); });
      const data = await request('/api/forecast-engine/status'); state.engine = data; state.events = data.events;
      text('nf-engine-status', '数学引擎已就绪'); $('nf-end').value = data.data_cutoff;
      $('nf-event').innerHTML = data.events.map((item) => `<option value="${esc(item.event_id)}">${esc(item.label)}</option>`).join('');
      if (data.events[0]) $('nf-mult').value = data.events[0].mult_base;
      try {
        const chronos = await request('/api/forecast-engine/chronos-status'); state.chronos = chronos;
        try { state.sarimax = await request('/api/forecast-engine/sarimax-status'); } catch (_) { state.sarimax = null; }
        $('nf-chronos-region').innerHTML = [chronos.region_all, ...chronos.provinces].map((x) => `<option value="${esc(x)}">${esc(x)}</option>`).join('');
        $('nf-chronos-energy').innerHTML = [...chronos.energies].reverse().map((x) => `<option value="${esc(x)}">${esc(x)}</option>`).join('');
        $('nf-chronos-cutoff').value = chronos.last_month; $('nf-chronos-cutoff').max = chronos.last_month;
      } catch (error) { setState('历史数据不可用', error.message, true); }
      mode('chronos');
      await restoreRuns(); refreshCompareHint();
      $('nf-run').disabled = false;
      loaded = true;
    } catch (error) { root.textContent = error.message + ' 请刷新页面重试。'; }
    finally { loading = false; }
  }
  document.addEventListener('view:enter', (event) => { if (event.detail.view === 'forecast-engine') load(); });
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', () => { if (location.hash === '#forecast-engine') load(); });
  else if (location.hash === '#forecast-engine') load();
}());
