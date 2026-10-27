'use strict';

const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const test = require('node:test');
const path = require('node:path');

const source = fs.readFileSync(path.join(__dirname, '../assets/home.js'), 'utf8').replace(/\r\n/g, '\n');
const markup = fs.readFileSync(path.join(__dirname, '../home.html'), 'utf8').replace(/\r\n/g, '\n');
const start = source.indexOf('  const ForecastView = (() => {') + '  const ForecastView = (() => {'.length;
const end = source.indexOf('    return { init, render, setYear, setMetric };', start);
assert.ok(start > 0 && end > start, 'ForecastView source boundary must be present');
const forecastSource = '(() => {' + source.slice(start, end) + '\nreturn { state, datasets, render, today, importAttachment, consumeJob, restoreLatestJob, resumeMonitoring, runForecastAgent, setYear, setMetric, requestJson }; })()';

function environment(fetchImpl) {
  const elements = new Map();
  const timers = new Map();
  const calls = [];
  let timer = 0;
  class Element {
    constructor(name = '') {
      this.name = name;
      this.value = '';
      this.disabled = false;
      this.hidden = false;
      this.innerHTML = '';
      this.textContent = '';
      this.children = [];
      this.dataset = {};
      this.classList = { toggle() {}, add() {}, remove() {} };
    }
    setAttribute(key, value) { this[key] = value; }
    append(...nodes) { nodes.forEach((n) => this.appendChild(n)); }
    appendChild(node) { this.children.push(node); node.parent = this; return node; }
    replaceChildren(...nodes) { this.children = nodes; }
    remove() { if (this.parent) this.parent.children = this.parent.children.filter((n) => n !== this); }
    click() { this.clicked = true; }
    addEventListener() {}
  }
  const get = (name) => {
    if (!elements.has(name)) elements.set(name, new Element(name));
    return elements.get(name);
  };
  get('forecast-target-year').value = '2027';
  get('forecast-annual-total').value = '2060';
  get('forecast-annual-action').value = 'keep';
  get('forecast-history-unit').value = 'vehicle';
  get('forecast-prompt').value = '输出2027年各月总量与新能源渗透率';
  const yearButtons = [2026, 2027].map((year) => { const el = get('year-' + year); el.dataset.forecastYear = String(year); return el; });
  const taskButtons = ['monthly', 'rolling', 'adjust', 'longterm', 'review'].map((task) => { const el = get('task-' + task); el.dataset.forecastTask = task; return el; });
  const metricButtons = ['volume', 'penetration'].map((metric) => { const el = get('metric-' + metric); el.dataset.forecastMetric = metric; return el; });
  const inputNames = ['forecast-target-year', 'forecast-annual-total', 'forecast-annual-action', 'forecast-history-unit', 'forecast-history-file', 'forecast-prompt'];
  class FixedDate extends Date {
    constructor(...args) { super(...(args.length ? args : ['2026-10-10T04:00:00Z'])); }
    static now() { return new Date('2026-10-10T04:00:00Z').getTime(); }
  }
  const context = {
    Intl, Date: FixedDate, URL, AbortController,
    location: { href: 'http://127.0.0.1:7860/#forecast', origin: 'http://127.0.0.1:7860' },
    Toast: { show(message, type) { calls.push({ toast: message, type }); } },
    setTimeout(fn) { const id = ++timer; timers.set(id, fn); return id; },
    clearTimeout(id) { timers.delete(id); },
    fetch: async (url, options) => {
      calls.push({ url, options });
      const result = await fetchImpl(url, options);
      return { ok: result.ok !== false, status: result.status || 200, json: async () => result.data };
    },
    document: {
      getElementById: get,
      createElement: (tag) => new Element(tag),
      querySelector: (selector) => get(selector),
      querySelectorAll(selector) {
        if (selector.includes('.forecast-composer input')) return [...inputNames.map(get), ...yearButtons, ...taskButtons];
        if (selector === '[data-forecast-year]') return yearButtons;
        if (selector === '[data-forecast-task]') return taskButtons;
        if (selector === '[data-forecast-metric]') return metricButtons;
        return [];
      },
      addEventListener() {},
      body: get('body'),
    },
  };
  return { view: vm.runInNewContext(forecastSource, context), get, calls, timers };
}

const history = { history_id: 'history-test', filename: '业务销量.xlsx', unit: 'vehicle', summary: { count: 176, complete_years: [2021, 2022, 2023, 2024, 2025], latest_period: '2026-08' }, warnings: ['已发布月份作为实际历史输入'] };
function completed(year = 2027) {
  const total = year === 2027 ? 2060 : 1960;
  return {
    run_id: 'forecast-test-' + year, status: 'completed', stage: '完成',
    validation: { status: 'passed' },
    steps: [{ id: 'validate', title: '独立校验', status: 'completed', summary: '通过' }],
    artifacts: [{ label: '下载Excel', url: '/api/forecast/download?run_id=test&kind=xlsx' }],
    result: {
      year, annual_total: total, as_of_date: '2026-10-10', history_window: [2021, 2022, 2023, 2024, 2025],
      method: { name: '历史中位数基准', total: '年度约束', penetration: '百分点趋势' },
      source_filename: history.filename, assumptions: ['同口径假设'], warnings: [],
      summary: { displayed_total_rounding_difference: 0.01 },
      rows: Array.from({ length: 12 }, (_, i) => ({ month: i + 1, total: total / 12, penetration: 50, nev: total / 24, traditional: total / 24, status: year === 2026 && i < 8 ? 'provided' : 'forecast' })),
    },
  };
}

test('initial view has no fabricated monthly result and uses Shanghai current date', () => {
  const env = environment(async () => ({ data: {} }));
  env.view.render();
  assert.equal(env.view.datasets[2027].rows.length, 0);
  assert.equal(env.get('forecast-penetration').textContent, '—');
  assert.equal(env.get('forecast-audit-boundary').textContent, '待校验');
  assert.equal(env.get('.forecast-download').disabled, true);
  assert.equal(env.view.today(), '2026-10-10');
});

test('only monthly and rolling scenarios are presented as runnable', () => {
  assert.match(markup, /data-forecast-task='monthly' data-forecast-availability='available'[\s\S]*?可运行/);
  assert.match(markup, /data-forecast-task='rolling' data-forecast-availability='available'[\s\S]*?可运行/);
  for (const task of ['adjust', 'longterm', 'review']) {
    assert.match(markup, new RegExp("data-forecast-task='" + task + "' data-forecast-availability='planned'[^>]*disabled[\\s\\S]*?规划中"));
  }
  assert.match(markup, /暂不提供预测结果或对话入口/);
});

test('Excel upload sends original bytes and exposes history metadata', async () => {
  const file = { name: '业务销量.xlsx', size: 40000 };
  const env = environment(async (url, options) => {
    assert.match(url, /^\/api\/forecast\/history\?filename=/);
    assert.match(url, /unit=vehicle/);
    assert.equal(options.body, file);
    assert.equal(options.headers['Content-Type'], 'application/octet-stream');
    return { data: history };
  });
  await env.view.importAttachment(file);
  assert.equal(env.view.state.history.history_id, history.history_id);
  assert.match(env.get('forecast-history-summary').innerHTML, /176 个月/);
  assert.match(env.get('forecast-history-summary').innerHTML, /2026-08/);
  assert.equal(env.view.state.uploading, false);
});

test('failed replacement upload retains previously connected history', async () => {
  const env = environment(async () => ({ ok: false, status: 400, data: { error: '缺少新能源字段' } }));
  env.view.state.history = history;
  await env.view.importAttachment({ name: '损坏.xlsx', size: 3000 });
  assert.equal(env.view.state.history, history);
  assert.match(env.get('forecast-history-summary').innerHTML, /业务销量.xlsx/);
  assert.ok(env.calls.some((c) => c.toast?.includes('缺少新能源字段')));
  assert.equal(env.get('.forecast-run').disabled, false);
});

test('completed status without passed validation cannot publish result or downloads', () => {
  const env = environment(async () => ({ data: {} }));
  const job = completed();
  job.validation.status = 'failed';
  env.view.consumeJob(job);
  assert.equal(env.view.datasets[2027].rows.length, 0);
  assert.equal(env.view.state.job.status, 'failed');
  assert.equal(env.get('forecast-artifacts').children.length, 0);
  assert.match(env.get('forecast-job-error').textContent, /独立校验/);
});

test('2026 provided rows show as published actuals and 2027 rows are forecasts', () => {
  const env = environment(async () => ({ data: {} }));
  env.view.consumeJob(completed(2026));
  const table2026 = env.get('forecast-table-body').innerHTML;
  assert.equal((table2026.match(/已发布实际/g) || []).length, 8);
  assert.equal((table2026.match(/基准预测/g) || []).length, 4);
  env.view.consumeJob(completed(2027));
  assert.equal((env.get('forecast-table-body').innerHTML.match(/基准预测/g) || []).length, 12);
  assert.equal(env.get('forecast-total').textContent, '2,060.00');
  assert.equal(env.get('forecast-penetration').textContent, '50.00');
  assert.match(env.get('forecast-table-caption').textContent, /舍入尾差 \+0.01/);
  assert.match(env.get('forecast-chart').innerHTML, />100%<\/text>/);
  assert.equal(env.get('forecast-artifacts').children.length, 1);
  assert.equal(env.get('.forecast-download').disabled, false);
});

test('failed job response is consumed as a failure instead of endless polling', async () => {
  const job = { run_id: 'forecast-failed', status: 'failed', error: '年度值小于已提供月份合计', steps: [], validation: { status: 'failed' } };
  const env = environment(async () => ({ data: job }));
  const response = await env.view.requestJson('/api/forecast/jobs?run_id=forecast-failed');
  assert.equal(env.view.consumeJob(response), true);
  assert.equal(env.view.state.running, false);
  assert.match(env.get('forecast-job-error').textContent, /年度值小于/);
  assert.equal(env.get('.forecast-resume').hidden, false);
});

test('reload restores a validated result without resubmitting calculation', async () => {
  const env = environment(async (url) => {
    assert.equal(url, '/api/forecast/jobs?latest=1');
    return { data: completed() };
  });
  await env.view.restoreLatestJob();
  assert.equal(env.view.datasets[2027].rows.length, 12);
  assert.equal(env.calls.filter((c) => c.url).length, 1);
  assert.equal(env.view.state.running, false);
});

test('recovery resumes a failed persisted run then publishes only its validated result', async () => {
  const failed = { run_id: 'forecast-test-2027', status: 'failed', error: '服务重启中断', steps: [] };
  const env = environment(async (url, options) => {
    if (url.startsWith('/api/forecast/jobs?run_id=')) return { data: failed };
    assert.equal(url, '/api/forecast/jobs/resume');
    assert.equal(JSON.parse(options.body).run_id, failed.run_id);
    return { data: completed() };
  });
  env.view.state.job = failed;
  await env.view.resumeMonitoring();
  assert.equal(env.view.datasets[2027].rows.length, 12);
  assert.equal(env.view.state.running, false);
});

test('starting baseline locks inputs and sends confirmed annual targets and draft status', async () => {
  const env = environment(async (url, options) => {
    if (url === '/api/forecast/jobs') {
      const payload = JSON.parse(options.body);
      assert.equal(payload.target_year, 2027);
      assert.equal(payload.annual_targets['2026'], 1960);
      assert.equal(payload.annual_targets['2027'], 2060);
      assert.equal(payload.allow_draft, true);
      assert.equal(payload.as_of_date, '2026-10-10');
      return { data: { run_id: 'forecast-running', status: 'running', steps: [] } };
    }
    return { data: { run_id: 'forecast-running', status: 'running', steps: [] } };
  });
  env.view.state.history = history;
  await env.view.runForecastAgent();
  assert.equal(env.view.state.running, true);
  assert.equal(env.get('forecast-target-year').disabled, true);
  assert.equal(env.get('forecast-history-file').disabled, true);
  assert.equal(env.get('.forecast-run').disabled, true);
  env.view.setYear(2026);
  assert.equal(env.view.state.year, 2027);
});

test('zero-total source month shows no penetration and creates a gap in the chart', () => {
  const env = environment(async () => ({ data: {} }));
  const job = completed(2026);
  const original = job.result.rows[5].total;
  job.result.rows[5] = { month: 6, total: 0, nev: 0, traditional: 0, penetration: null, status: 'provided' };
  job.result.rows[11].total += original;
  job.result.rows[11].nev += original / 2;
  job.result.rows[11].traditional += original / 2;
  env.view.consumeJob(job);
  assert.equal(env.view.state.job.status, 'completed');
  assert.match(env.get('forecast-table-body').innerHTML, /<th scope="row">6月<\/th>.*?<td class="is-number">—<\/td>/);
  assert.equal((env.get('forecast-chart').innerHTML.match(/<polyline /g) || []).length, 2);
  assert.equal((env.get('forecast-chart').innerHTML.match(/<circle /g) || []).length, 11);
  assert.doesNotMatch(env.get('forecast-chart').innerHTML, /NaN|Infinity|6月：0\.00%/);
  assert.match(env.get('forecast-table-caption').textContent, /折线在该月断开/);
  env.view.setMetric('penetration');
  assert.equal((env.get('forecast-chart').innerHTML.match(/<polyline /g) || []).length, 2);
});

test('missing penetration for a positive-total month is rejected', () => {
  const env = environment(async () => ({ data: {} }));
  const job = completed();
  job.result.rows[5].penetration = null;
  env.view.consumeJob(job);
  assert.equal(env.view.state.job.status, 'failed');
  assert.equal(env.view.datasets[2027].rows.length, 0);
});

test('chat receives normalized records with units independent of the original file', async () => {
  const env = environment(async (url, options) => {
    if (url.startsWith('/api/forecast/history?')) return { data: { ...history, records_unit: '万辆', records: [{ year: 2025, month: 1, total: 100, nev: 50 }] } };
    assert.equal(url, '/api/chat');
    const payload = JSON.parse(options.body);
    assert.match(payload.question, /"records_unit":"万辆"/);
    assert.match(payload.question, /"original_file_unit":"vehicle"/);
    assert.match(payload.question, /禁止再次换算/);
    assert.doesNotMatch(payload.question, /"unit":"vehicle"/);
    return { data: { answer: '已按规范化万辆记录整理。' } };
  });
  env.view.state.history = history;
  env.view.state.task = 'longterm';
  await env.view.runForecastAgent();
  assert.equal(env.calls.filter((c) => c.url === '/api/chat').length, 1);
  assert.equal(env.view.state.running, false);
});
