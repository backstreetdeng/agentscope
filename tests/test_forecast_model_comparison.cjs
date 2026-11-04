'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');

const source = fs.readFileSync(path.join(__dirname, '../assets/forecast-engine.js'), 'utf8')
  .replace("  document.addEventListener('view:enter'", "  globalThis.testApi = { state, compareModels, rememberRun };\n  document.addEventListener('view:enter'");

function setup() {
  const elements = new Map();
  const get = (id) => {
    if (!elements.has(id)) elements.set(id, { value:'', hidden:false, textContent:'', innerHTML:'', style:{} });
    return elements.get(id);
  };
  get('nf-chronos-region').value = '广东'; get('nf-chronos-energy').value = '插混';
  get('nf-chronos-cutoff').value = '2026-09'; get('nf-chronos-horizon').value = '1';
  const storage = new Map();
  const ctx = { document:{ getElementById:get, addEventListener(){}, readyState:'loading' },
    localStorage:{setItem:(k,v)=>storage.set(k,v)}, setTimeout, clearTimeout, AbortController, Intl, URL };
  vm.runInNewContext(source, ctx);
  ctx.testApi.state.chronos = { source_sha256:'hash-1' };
  const job = (model, overrides={}) => ({ run_id:model+'-'+(model==='chronos'?'a':'b').repeat(32), status:'completed', operation:'forecast', data:{
    source_sha256:'hash-1', history_start:'2012-01', data_cutoff:'2026-09', province:'广东', energy:'插混', metric:'零售', unit:'辆',
    forecast:[{month:'2026-10',p10:10,p50:20,p90:30}], ...overrides } });
  return { api:ctx.testApi, get, storage, job };
}

test('same-scope forecasts compare their differently labelled outputs', async () => {
  const {api,get,job} = setup();
  api.state.modelRuns.forecast.chronos=job('chronos'); api.state.modelRuns.forecast.sarimax=job('sarimax');
  await api.compareModels();
  assert.match(get('nf-comparison').innerHTML, /同条件销量预测比较/);
  assert.match(get('nf-comparison').innerHTML, /Chronos-2 中位数/);
  assert.match(get('nf-comparison').innerHTML, /SARIMAX 均值/);
});

test('different scope, source version or forecast period are not compared', async () => {
  for (const overrides of [{province:'上海'}, {source_sha256:'hash-2'}, {forecast:[{month:'2026-11',p10:10,p50:20,p90:30}]}]) {
    const {api,get,job} = setup();
    api.state.modelRuns.forecast.chronos=job('chronos'); api.state.modelRuns.forecast.sarimax=job('sarimax',overrides);
    await api.compareModels();
    assert.doesNotMatch(get('nf-comparison').innerHTML, /同条件销量预测比较/);
    assert.ok(get('nf-comparison').textContent);
  }
});

test('browser storage contains task IDs but no forecast or historical data', () => {
  const {api,storage,job} = setup();
  api.rememberRun(job('chronos'), 'forecast', 'chronos');
  const saved = JSON.parse([...storage.values()][0]);
  assert.match(saved.ids.forecast.chronos, /^chronos-[a-f0-9]{32}$/);
  assert.doesNotMatch(JSON.stringify(saved), /广东|插混|p50|2026-10/);
});
