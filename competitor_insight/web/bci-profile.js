/* ==========================================================================
   竞品洞察 tab ② · 用户洞察档案（bci-profile）
   自包含模块，暴露 window.BciProfile。不 import bci.js；通过
   window.BCI_SCOPE / localStorage['bci.scope'] / bci:scope-applied 只读 scope。
   D6 前不触碰共用文件；接入时由 home.html 引入并在 bci 视图内 init。

   安全约定：
   - 档案值 / 原话 / 模板名一律 textContent 渲染，禁止 innerHTML 拼接模型输出；
   - 「找原话」命中词用文本节点拆分 + <mark>，禁止整段 innerHTML。
   ========================================================================== */
(function () {
  'use strict';

  const API_BASE = '/api/bci/archive';
  const SCOPE_KEY = 'bci.scope';
  const NO_SOURCE_PREFIX = '本期无来源';

  const GROUPS_LABEL = {
    answer: '答案',
    evidence: '访谈证据',
    tag_evidence: '标签证据',
    archive: '档案值',
  };

  const state = {
    root: null,
    templateId: '',
    canGenerate: false,
    template: null,
    respondents: [],
    total: 0,
    keyword: '',
    pageSize: 200,
    selected: new Set(),
    currentId: null,
    detail: null,
    runId: null,
    runTimer: null,
    runSkipped: 0,
    bound: false,
  };

  /* ------------------------------------------------ 工具 */

  function qs(sel, root) { return (root || document).querySelector(sel); }
  function qsa(sel, root) { return Array.prototype.slice.call((root || document).querySelectorAll(sel)); }
  function el(tag, cls, text) {
    const node = document.createElement(tag);
    if (cls) node.className = cls;
    if (text !== undefined && text !== null) node.textContent = String(text);
    return node;
  }
  function fmtDate(value) {
    if (!value) return '';
    const d = new Date(value);
    if (Number.isNaN(d.getTime())) return String(value);
    const pad = (n) => String(n).padStart(2, '0');
    return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`;
  }
  function fmtNum(value) {
    if (value === null || value === undefined || value === '') return '';
    const n = Number(value);
    return Number.isNaN(n) ? String(value) : `${Math.round(n * 100) / 100}%`;
  }

  // 返回完整 scope 对象（{version,datasources}），与 bci:scope-applied 的 detail 形状一致。
  function readScope() {
    try {
      const stored = JSON.parse(localStorage.getItem(SCOPE_KEY) || 'null');
      if (stored && stored.datasources) return stored;
    } catch (e) { /* ignore */ }
    if (window.BCI_SCOPE && window.BCI_SCOPE.datasources) return window.BCI_SCOPE;
    return null;
  }

  async function api(path, options) {
    const resp = await fetch(API_BASE + path, options);
    const contentType = resp.headers.get('content-type') || '';
    if (contentType.indexOf('application/json') >= 0) {
      const payload = await resp.json();
      if (!resp.ok || payload.ok === false) {
        const err = (payload.error && payload.error.message) || `HTTP ${resp.status}`;
        const ex = new Error(err);
        ex.code = payload.error && payload.error.code;
        ex.payload = payload.error || null;
        throw ex;
      }
      return payload.data;
    }
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
    return resp;
  }

  /* ------------------------------------------------ 渲染：空态 / 阻塞 */

  function renderBlocked(message, action) {
    const body = qs('.bp-doc__body', state.root);
    body.innerHTML = '';
    const empty = el('div', 'bp-empty');
    empty.appendChild(el('strong', '', '洞察档案暂不可用'));
    const p = el('p', '', message);
    empty.appendChild(p);
    if (action) {
      const btn = el('button', 'bp-btn bp-btn--primary', action.label);
      btn.addEventListener('click', action.run);
      empty.appendChild(btn);
    }
    body.appendChild(empty);
  }

  function renderEmpty(message) {
    const body = qs('.bp-doc__body', state.root);
    body.innerHTML = '';
    const empty = el('div', 'bp-empty');
    empty.appendChild(el('strong', '', '尚未生成档案'));
    empty.appendChild(el('p', '', message));
    const noSourceMap = state.template && state.template.source_map_ready === false;
    if (noSourceMap) {
      empty.appendChild(el('p', '', '当前模板暂不支持自动生成（缺题项映射），请切换到「用户洞察档案」模板。'));
    } else {
      const btn = el('button', 'bp-btn bp-btn--primary', '生成本人档案');
      btn.addEventListener('click', () => {
        if (!state.currentId) return;
        if (!state.canGenerate) { showAlert('本次未选入 2025 年定性解析数据，暂不能生成。'); return; }
        startGenerate([state.currentId], 'single');
      });
      empty.appendChild(btn);
    }
    body.appendChild(empty);
  }

  function renderLoading() {
    const body = qs('.bp-doc__body', state.root);
    body.innerHTML = '';
    const sk = el('div', 'bp-skeleton');
    for (let i = 0; i < 8; i += 1) sk.appendChild(el('i'));
    body.appendChild(sk);
  }

  /* ------------------------------------------------ 渲染：受访者列表 */

  function renderList() {
    const items = qs('.bp-list__items', state.root);
    items.innerHTML = '';
    const list = state.respondents;
    if (!list.length) {
      items.appendChild(el('li', 'bp-empty', '没有匹配的受访者'));
      return;
    }
    list.forEach((row) => {
      const li = el('li', 'bp-item');
      li.classList.toggle('is-active', row.interview_id === state.currentId);
      const cb = document.createElement('input');
      cb.type = 'checkbox';
      cb.checked = state.selected.has(row.interview_id);
      cb.addEventListener('change', () => {
        if (cb.checked) state.selected.add(row.interview_id);
        else state.selected.delete(row.interview_id);
        updateSelectionUI();
        if (cb.checked && row.interview_id !== state.currentId) selectPerson(row.interview_id);
      });
      li.appendChild(cb);

      const main = el('button', 'bp-item__main');
      const line = el('span', 'bp-item__line');
      line.appendChild(el('span', 'bp-item__code', row.respondent_code || row.interview_id));
      const city = [row.city, row.vehicle_model].filter(Boolean).join(' · ');
      if (city) line.appendChild(el('span', 'bp-item__city', city));
      main.appendChild(line);
      main.addEventListener('click', () => selectPerson(row.interview_id));
      li.appendChild(main);

      if (row.archive) {
        const badge = el('span', 'bp-item__status is-' + row.archive.status, {
          ready: '已归档',
          partial: '部分',
          failed: '失败',
          stale: '旧版',
        }[row.archive.status] || row.archive.status);
        li.appendChild(badge);
      } else {
        li.appendChild(el('span', 'bp-item__status is-none', '未生成'));
      }
      items.appendChild(li);
    });

    const head = qs('.bp-list__head', state.root);
    const title = qs('.bp-list__title', head);
    title.textContent = '';
    title.appendChild(document.createTextNode('用户列表 · ' + state.total + ' 人'));
    title.appendChild(el('span', '', ' · 已勾选 ' + state.selected.size));
    syncSelectAll();
  }

  function syncSelectAll() {
    const box = qs('[data-bp-select-all]', state.root);
    if (!box) return;
    const ids = state.respondents.map((r) => r.interview_id);
    const picked = ids.filter((id) => state.selected.has(id)).length;
    box.checked = ids.length > 0 && picked === ids.length;
    box.indeterminate = picked > 0 && picked < ids.length;
    box.disabled = !ids.length || !!state.runId;
    const label = qs('[data-bp-select-label]', state.root);
    if (label) label.textContent = '已勾选 ' + state.selected.size + ' / ' + state.total;
  }

  function updateSelectionUI() {
    const title = qs('.bp-list__title', state.root);
    if (title && title.childNodes[1]) title.childNodes[1].textContent = ' · 已勾选 ' + state.selected.size;
    qsa('.bp-item', state.root).forEach((li) => {
      const cb = qs('input[type="checkbox"]', li);
      li.classList.toggle('is-selected', cb.checked);
    });
    updateActionState();
  }

  /* ------------------------------------------------ 渲染：档案表 */

  function substName(name) {
    if (!name) return name || '';
    const naming = state.detail && state.detail.naming;
    if (!naming) return name;
    return String(name)
      .split('{brand}').join(naming.brand || '{brand}')
      .split('{vehicle}').join(naming.vehicle || '{vehicle}');
  }

  function renderDoc() {
    const body = qs('.bp-doc__body', state.root);
    body.innerHTML = '';
    const detail = state.detail;
    qs('.bp-doc__head h3', state.root).textContent = '用户洞察档案';
    qs('.bp-doc__meta', state.root).textContent = buildMeta(state.currentId);

    if (!detail || !detail.archive) {
      if (!state.currentId) {
        const empty = el('div', 'bp-empty');
        empty.appendChild(el('strong', '', '没有可查看的受访者'));
        empty.appendChild(el('p', '', state.keyword ? '当前搜索没有匹配结果，试试清空搜索。' : '访谈库中暂无可展示的受访者。'));
        body.appendChild(empty);
        return;
      }
      renderEmpty('当前受访者尚未生成档案。生成后按模板 43 个维度展示，并保留原话证据。');
      return;
    }

    const archive = detail.archive || {};
    const dims = (state.template && state.template.dimensions) || [];

    // 顶部横幅
    const bannerHost = qs('.bp-doc', state.root);
    qsa('.bp-banner', bannerHost).forEach((b) => b.remove());
    if (archive.status === 'partial') {
      bannerHost.insertBefore(el('div', 'bp-banner', '部分必填维度未归档，缺失行已标黄。'), body);
    } else if (archive.status === 'failed') {
      bannerHost.insertBefore(el('div', 'bp-banner', '本次生成失败，未落库。可重新生成。'), body);
    } else if (archive.status === 'stale') {
      bannerHost.insertBefore(el('div', 'bp-banner bp-banner--info', '模板已升级或切换，当前档案为旧版本。可重新归档。'), body);
    }

    const table = el('table', 'bp-table');
    const thead = document.createElement('thead');
    const tr = document.createElement('tr');
    tr.appendChild(el('th', '', '模块'));
    tr.appendChild(el('th', '', '子项'));
    tr.appendChild(el('th', '', '档案内容'));
    thead.appendChild(tr);
    table.appendChild(thead);

    const tbody = document.createElement('tbody');
    const groups = {};
    (state.template.groups || []).forEach((g) => { groups[g.id] = substName(g.name || g.id); });
    const fields = detail.fields || [];
    const byId = {};
    fields.forEach((f) => { byId[f.dimension_id] = f; });

    let lastGroupCell = null;
    let lastGroupId = null;
    dims.forEach((dim) => {
      const field = byId[dim.id] || null;
      const rowCls = ['bp-row--' + rowClass(field, dim)];
      const tr2 = document.createElement('tr');
      if (rowCls[0] !== 'bp-row--normal') tr2.className = rowCls[0];

      // 模块列按模板 groups 顺序合并连续同组行（rowspan）。
      if (dim.group === lastGroupId && lastGroupCell) {
        lastGroupCell.rowSpan += 1;
      } else {
        lastGroupCell = el('td', 'bp-cell--group', groups[dim.group] || dim.group || '');
        tr2.appendChild(lastGroupCell);
        lastGroupId = dim.group;
      }
      const dimCell = el('td', 'bp-cell--dim', substName(dim.name) || dim.id);
      const valueCell = el('td', 'bp-cell--value');

      if (!field) {
        valueCell.appendChild(el('span', 'bp-value', '未生成'));
      } else if (field.source_ref && field.source_ref.no_source_scope === 'template') {
        valueCell.appendChild(el('span', 'bp-value', NO_SOURCE_PREFIX));
        valueCell.appendChild(el('div', 'bp-reason', field.no_data_reason || ''));
      } else {
        valueCell.appendChild(el('span', 'bp-value', displayValue(field)));
        if (field.fill_mode === 'none' && field.no_data_reason) {
          valueCell.appendChild(el('div', 'bp-reason', field.no_data_reason));
        }
        if (field.fill_mode === 'metadata') {
          const f = field.source_ref && field.source_ref.fields;
          valueCell.appendChild(el('div', 'bp-note', '来源：' + (f && f.length ? f.map(fieldName).join('、') : '元数据字段')));
        } else if (field.fill_mode === 'tag') {
          const names = (field.source_ref && field.source_ref.tag_names) || [];
          valueCell.appendChild(el('div', 'bp-note', '来源：' + (names.length ? names.join('、') : '标签')));
        }
        if (field.evidence_refs && field.evidence_refs.length) {
          valueCell.appendChild(buildChips(field));
        }
      }

      tr2.appendChild(dimCell);
      tr2.appendChild(valueCell);
      tbody.appendChild(tr2);
    });

    table.appendChild(tbody);
    body.appendChild(table);
  }

  function rowClass(field, dim) {
    if (!field) return 'normal';
    if (field.source_ref && field.source_ref.no_source_scope === 'template') return 'nosource';
    if (field.dimension_id === 'satisfaction_score' && field.score_source === 'missing') return 'warn';
    if (field.fill_mode === 'none') return 'missing';
    return 'normal';
  }

  function displayValue(field) {
    if (!field) return '';
    if (field.display_value !== undefined && field.display_value !== null && field.display_value !== '') {
      return field.display_value;
    }
    if (field.value_json && typeof field.value_json === 'object' && field.value_json.score !== undefined && field.value_json.score !== null) {
      return String(field.value_json.score) + ' 分';
    }
    return field.value_text || '';
  }

  function fieldName(field) {
    const map = { purchase_type: '购车类型', city: '城市', vehicle_model: '车型', age_range: '年龄' };
    return map[field] || field;
  }

  function buildChips(field) {
    const wrap = el('div', 'bp-chips');
    field.evidence_refs.forEach((ref, index) => {
      const chip = el('button', 'bp-chip' + (ref.source_missing ? ' is-missing' : ''), '证据 ' + (index + 1) + (ref.source_missing ? '（来源已失效）' : ''));
      chip.addEventListener('click', (ev) => {
        ev.stopPropagation();
        openPopover(chip, field, ref);
      });
      wrap.appendChild(chip);
    });
    return wrap;
  }

  function buildMeta(interviewId) {
    const row = state.respondents.find((r) => r.interview_id === interviewId);
    if (!row) return '';
    const parts = [row.respondent_code || interviewId];
    if (row.city) parts.push(row.city);
    if (row.vehicle_model) parts.push(row.vehicle_model);
    if (row.purchase_type) parts.push(row.purchase_type);
    const archive = state.detail && state.detail.archive;
    if (archive) {
      if (archive.generated_at) parts.push('生成于 ' + fmtDate(archive.generated_at));
      if (archive.coverage_required !== undefined && archive.coverage_required !== null) {
        parts.push('覆盖率 ' + fmtNum(archive.coverage_required));
      }
      if (archive.revision > 1) parts.push('第 ' + archive.revision + ' 版');
    }
    return parts.join(' · ');
  }

  /* ------------------------------------------------ 证据 popover */

  function openPopover(anchor, field, ref) {
    closePopover();
    const pop = el('div', 'bp-pop');
    pop.appendChild(el('div', 'bp-pop__title', field && field.dimension_id ? dimName(field.dimension_id) : '证据'));
    const meta = ['Q' + (ref.question_id ?? '?'), ref.speaker || '未知', kindLabel(ref.kind)].filter(Boolean).join(' · ');
    pop.appendChild(el('div', 'bp-pop__meta', meta));
    if (ref.quote) pop.appendChild(el('div', 'bp-pop__quote', '「' + ref.quote + '」'));
    if (ref.source_missing) pop.appendChild(el('div', 'bp-pop__lost', '原话来源已失效，当前保留生成时的快照。'));

    document.body.appendChild(pop);
    const rect = anchor.getBoundingClientRect();
    const left = Math.min(rect.left, window.innerWidth - 400);
    const top = Math.min(rect.bottom + 6, window.innerHeight - pop.offsetHeight - 12);
    pop.style.left = Math.max(8, left) + 'px';
    pop.style.top = Math.max(8, top) + 'px';

    const onDoc = (ev) => {
      if (!pop.contains(ev.target)) {
        closePopover();
        document.removeEventListener('click', onDoc, true);
        window.removeEventListener('scroll', onDoc, true);
      }
    };
    document.addEventListener('click', onDoc, true);
    window.addEventListener('scroll', onDoc, true);
    state._popCleanup = () => { document.removeEventListener('click', onDoc, true); window.removeEventListener('scroll', onDoc, true); };
  }

  function closePopover() {
    if (state._popCleanup) { state._popCleanup(); state._popCleanup = null; }
    qsa('.bp-pop', document).forEach((p) => p.remove());
  }

  function dimName(id) {
    const dims = (state.template && state.template.dimensions) || [];
    const found = dims.find((d) => d.id === id);
    return found ? (substName(found.name) || id) : id;
  }

  function kindLabel(kind) {
    return GROUPS_LABEL[kind] || kind;
  }

  /* ------------------------------------------------ 找原话 */

  function renderQuote(container, data) {
    container.innerHTML = '';
    if (!data || !data.total) {
      container.appendChild(el('div', 'bp-quote__empty', '未找到包含该关键词的原话。'));
      return;
    }
    const order = ['answer', 'evidence', 'tag_evidence', 'archive'];
    const buckets = {};
    data.items.forEach((item) => {
      const key = order.indexOf(item.kind) >= 0 ? item.kind : 'archive';
      (buckets[key] = buckets[key] || []).push(item);
    });
    order.forEach((key) => {
      if (!buckets[key]) return;
      const group = el('div', 'bp-quote__group');
      group.appendChild(el('h5', '', GROUPS_LABEL[key] + ' · ' + buckets[key].length));
      buckets[key].forEach((item) => {
        const node = el('div', 'bp-quote__item');
        const quote = highlight(item.quote || item.value_text || '', data.keyword);
        node.appendChild(quote);
        const metaBits = [];
        const multiScope = !data.interview_ids || data.interview_ids.length !== 1;
        if (multiScope && item.interview_id) metaBits.push(item.interview_id);
        if (item.question_id) metaBits.push('Q' + item.question_id);
        if (item.speaker) metaBits.push(item.speaker);
        if (item.dimension_id) metaBits.push('维度：' + dimName(item.dimension_id));
        node.appendChild(el('div', 'bp-quote__meta', metaBits.join(' · ')));
        group.appendChild(node);
      });
      container.appendChild(group);
    });
  }

  function highlight(text, keyword) {
    const wrap = document.createElement('span');
    const lower = text.toLowerCase();
    const needle = keyword.toLowerCase();
    let index = 0;
    let pos;
    while ((pos = lower.indexOf(needle, index)) >= 0) {
      if (pos > index) wrap.appendChild(document.createTextNode(text.slice(index, pos)));
      const mark = document.createElement('mark');
      mark.textContent = text.slice(pos, pos + needle.length);
      wrap.appendChild(mark);
      index = pos + needle.length;
    }
    if (index < text.length) wrap.appendChild(document.createTextNode(text.slice(index)));
    return wrap;
  }

  /* ------------------------------------------------ 生成 / 轮询 */

  async function startGenerate(ids, mode, options) {
    const opts = options || {};
    if (!state.canGenerate) {
      showAlert('本次未选入 2025 年定性解析数据，暂不能生成。');
      return;
    }
    if (state.runId) return;
    try {
      const payload = await api('/generate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          interview_ids: ids,
          template_id: state.templateId,
          mode: mode,
          force: opts.force !== false,
        }),
      });
      state.runId = payload.run_id;
      state.runSkipped = payload.skipped || 0;
      updateActionState();
      showRunPanel(payload, opts);
      pollRun();
    } catch (err) {
      if (err.code === 'run_in_progress') {
        state.runId = err.payload.run_id;
        state.runSkipped = 0;
        updateActionState();
        showRunPanel({ total: 0, skipped: 0 }, opts);
        pollRun();
      } else {
        showAlert(err.message, true);
      }
    }
  }

  function showRunPanel(payload, options) {
    const opts = options || {};
    const panel = qs('.bp-run', state.root);
    panel.hidden = false;
    const summary = qs('.bp-run__summary', panel);
    summary.hidden = true;
    summary.innerHTML = '';
    const log = qs('.bp-run__log', panel);
    log.innerHTML = '';
    setRunHead(panel, opts.batch ? '正在批量归档' : '正在归档', payload.total, 0, 0);
    const abort = qs('[data-bp-run-abort]', panel);
    abort.hidden = false;
    abort.disabled = false;
    abort.textContent = '中止';
    qs('[data-bp-run-close]', panel).hidden = true;
    if (payload.skipped) {
      log.appendChild(logLine({
        interview_id: '-', status: 'skipped', error_text: '已有档案，跳过 ' + payload.skipped + ' 人',
      }));
    }
  }

  function setRunHead(panel, title, total, done, failed) {
    qs('.bp-run__title', panel).textContent = title + (total ? '（实际 ' + total + ' 人）' : '');
    qs('.bp-run__counts', panel).textContent = '已完成 ' + done + '/' + (total || 0) + ' · 失败 ' + failed;
  }

  function logLine(item) {
    const li = document.createElement('li');
    li.className = 'is-' + (item.status || 'running');
    const code = item.interview_id === '-' ? '系统' : (item.interview_id || '');
    li.appendChild(el('span', '', code));
    const label = { done: '完成', failed: '失败', running: '生成中', skipped: '跳过' }[item.status] || item.status;
    const raw = item.error_text || item.error || '';
    li.appendChild(el('span', '', label + (raw ? '：' + itemErrorText(raw) : '')));
    return li;
  }

  function itemErrorText(raw) {
    if (!raw) return '';
    const text = String(raw);
    const sep = text.indexOf(':');
    const code = sep >= 0 ? text.slice(0, sep) : text;
    const detail = sep >= 0 ? text.slice(sep + 1).trim() : '';
    const mapped = ITEM_ERROR_TEXT[code];
    if (!mapped) return text;
    return mapped + (detail ? '（' + detail + '）' : '');
  }

  function pollRun() {
    if (!state.runId) return;
    const tick = async () => {
      try {
        const data = await api('/run?run_id=' + encodeURIComponent(state.runId));
        const panel = qs('.bp-run', state.root);
        panel.hidden = false;
        qs('.bp-run__bar i', panel).style.width = data.progress + '%';
        setRunHead(panel, runTitle(data), data.total, data.done, data.failed);
        const log = qs('.bp-run__log', panel);
        log.innerHTML = '';
        (data.items || []).forEach((item) => log.appendChild(logLine(item)));
        if (isTerminal(data.status)) await finishRun(panel, data);
      } catch (err) {
        if (state.runTimer) { clearInterval(state.runTimer); state.runTimer = null; }
        state.runId = null;
        updateActionState();
        showAlert('读取运行状态失败：' + err.message, true);
      }
    };
    if (state.runTimer) clearInterval(state.runTimer);
    tick();
    state.runTimer = setInterval(tick, 1500);
  }

  function isTerminal(status) {
    return status === 'completed' || status === 'partial'
      || status === 'failed' || status === 'cancelled';
  }

  async function finishRun(panel, data) {
    state.runId = null;
    if (state.runTimer) { clearInterval(state.runTimer); state.runTimer = null; }
    updateActionState();
    qs('[data-bp-run-abort]', panel).hidden = true;
    qs('[data-bp-run-close]', panel).hidden = false;
    // 先刷新列表再出结果卡，避免「结果已成功、左侧仍显示未生成」的矛盾画面
    try {
      await refresh();
    } catch (err) { /* 刷新失败不阻塞结果展示，用户可手动重新加载 */ }
    const box = qs('.bp-run__summary', panel);
    box.innerHTML = '';
    box.hidden = false;
    box.classList.toggle('is-error', data.status === 'failed');
    box.appendChild(el('div', 'bp-run__summary-title', runResultMessage(data)));
    const failed = (data.items || []).filter((i) => i.status === 'failed');
    if (failed.length) {
      const list = el('ul', 'bp-run__failed');
      failed.forEach((item) => {
        list.appendChild(el('li', '', (item.interview_id || '?') + '：' +
          (itemErrorText(item.error_text || '') || '未知原因')));
      });
      box.appendChild(list);
    }
  }

  async function abortRun() {
    if (!state.runId) return;
    const panel = qs('.bp-run', state.root);
    const btn = qs('[data-bp-run-abort]', panel);
    btn.disabled = true;
    btn.textContent = '中止中…';
    try {
      await api('/cancel', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ run_id: state.runId }),
      });
    } catch (err) {
      btn.disabled = false;
      btn.textContent = '中止';
      showAlert('中止失败：' + err.message, true);
    }
  }

  function runTitle(data) {
    const map = {
      queued: '排队中', running: '正在归档', completed: '归档完成',
      partial: '部分完成', failed: '失败', cancelled: '已中止',
    };
    return map[data.status] || data.status;
  }

  const ITEM_ERROR_TEXT = {
    missing_evidence: '模型引用了无效证据 ID，被证据门拦截（防编造原话），可重试一次',
    cross_interview_or_fabricated_evidence: '模型引用了不属于该受访者的证据，已拒绝落库',
    invalid_enum: '模型返回了不在允许取值内的内容',
    llm_client_required: '模型客户端未配置',
    interview_not_found: '受访者不存在',
    database_unavailable: '数据库不可用',
  };

  function runResultMessage(data) {
    const total = Number(data.total || 0);
    const done = Number(data.done || 0);
    const failed = Number(data.failed || 0);
    const skipped = Number(data.skipped || 0);
    const extraSkip = state.runSkipped ? '；另有 ' + state.runSkipped + ' 人因已有档案被跳过' : '';
    const counts = '成功 ' + done + ' 人 · 失败 ' + failed + ' 人'
      + (skipped ? ' · 中止跳过 ' + skipped + ' 人' : '');
    if (data.status === 'completed') return '归档完成：共 ' + total + ' 人，' + counts + extraSkip + '。';
    if (data.status === 'partial') return '部分完成：共 ' + total + ' 人，' + counts + extraSkip + '。失败原因见下方列表。';
    if (data.status === 'cancelled') {
      const rest = Math.max(0, total - done - failed - skipped);
      return '已中止：共 ' + total + ' 人，' + counts + (rest ? ' · 剩余 ' + rest + ' 人未处理' : '') + extraSkip + '。';
    }
    return '归档失败：共 ' + total + ' 人，' + counts + extraSkip + '。';
  }

  function showAlert(message, isError) {
    qsa('.bp-alert', state.root).forEach((node) => node.remove());
    const alert = el('div', 'bp-alert' + (isError ? ' bp-alert--error' : ''));
    alert.appendChild(el('span', '', message));
    const close = el('button', 'bp-alert__close', '×');
    close.addEventListener('click', () => alert.remove());
    alert.appendChild(close);
    const host = qs('.bp-run', state.root);
    host.insertAdjacentElement('beforebegin', alert);
  }

  /* ------------------------------------------------ 数据加载 */

  async function refresh() {
    await loadTemplate();
    await loadRespondents();
    if (!state.currentId || !state.respondents.some((r) => r.interview_id === state.currentId)) {
      state.currentId = state.respondents.length ? state.respondents[0].interview_id : null;
    }
    await loadDetail();
    renderToolbar();
    renderList();
    renderDoc();
    updateSelectionUI();
  }

  function renderToolbar() {
    const strong = qs('.bp-scope__template', state.root);
    const count = qs('.bp-scope__count', state.root);
    if (!state.template) {
      strong.textContent = '加载中…';
      count.textContent = '';
      return;
    }
    strong.textContent = (state.template.label || state.template.template_id) + ' ' + (state.template.version || '');
    count.textContent = ' · ' + state.total + ' 人 · ' + state.template.dimension_count + ' 维';
  }

  async function loadTemplate() {
    const query = state.templateId ? '?template_id=' + encodeURIComponent(state.templateId) : '';
    const data = await api('/template' + query);
    state.template = data;
    state.templateId = data.template_id;
  }

  async function loadRespondents() {
    const query = new URLSearchParams({
      template_id: state.templateId,
      limit: String(state.pageSize),
    });
    if (state.keyword) query.set('keyword', state.keyword);
    const data = await api('/respondents?' + query.toString());
    state.respondents = data.items;
    state.total = data.total;
  }

  async function loadDetail() {
    if (!state.currentId) {
      state.detail = null;
      return;
    }
    const data = await api(
      '/detail?interview_id=' + encodeURIComponent(state.currentId) +
      '&template_id=' + encodeURIComponent(state.templateId)
    );
    state.detail = data;
  }

  function selectPerson(interviewId) {
    if (!interviewId) return;
    state.currentId = interviewId;
    renderList();
    renderLoading();
    loadDetail()
      .then(() => { renderDoc(); updateActionState(); })
      .catch((err) => showAlert(err.message, true));
  }

  /* ------------------------------------------------ 导出 */

  async function postExport(ids, format) {
    const resp = await fetch(API_BASE + '/export', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ interview_ids: ids, template_id: state.templateId, format: format }),
    });
    const type = resp.headers.get('content-type') || '';
    if (type.indexOf('application/json') >= 0) {
      const payload = await resp.json();
      const err = new Error((payload.error && payload.error.message) || '导出失败');
      err.code = payload.error && payload.error.code;
      err.payload = payload.error || null;
      throw err;
    }
    if (!resp.ok) throw new Error('导出失败（HTTP ' + resp.status + '）');
    const blob = await resp.blob();
    return { blob: blob, filename: filenameFrom(resp.headers.get('content-disposition')) };
  }

  function filenameFrom(header) {
    if (!header) return '';
    const star = /filename\*=UTF-8''([^;]+)/i.exec(header);
    if (star) {
      try { return decodeURIComponent(star[1]); } catch (e) { return star[1]; }
    }
    const plain = /filename="?([^";]+)"?/i.exec(header);
    return plain ? plain[1] : '';
  }

  async function exportXlsx() {
    if (!state.selected.size) {
      showAlert('请先在左侧勾选至少一位受访者。');
      return;
    }
    try {
      const result = await postExport(Array.from(state.selected), 'xlsx');
      downloadBlob(result.blob, result.filename || '用户洞察档案.xlsx');
    } catch (err) {
      if (err.code === 'archive_missing') {
        showAlert('部分受访者还没有档案，请先生成：' + (err.payload.interview_ids || []).join('、'));
      } else {
        showAlert(err.message, true);
      }
    }
  }

  async function exportMd() {
    if (!state.currentId) {
      showAlert('请先选择一位受访者。');
      return;
    }
    try {
      const result = await postExport([state.currentId], 'md');
      downloadBlob(result.blob, result.filename || '用户洞察档案.md');
    } catch (err) {
      showAlert(err.message, true);
    }
  }

  function downloadBlob(blob, filename) {
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    a.remove();
    setTimeout(() => URL.revokeObjectURL(url), 4000);
  }

  function updateActionState() {
    const actions = qs('.bp-actions', state.root);
    if (!actions) return;
    const button = (name) => qs('[data-bp-action="' + name + '"]', actions);
    const canGenerate = state.canGenerate && !!state.template && !state.runId;
    const noSourceMap = !!state.template && state.template.source_map_ready === false;
    const current = state.respondents.find((r) => r.interview_id === state.currentId) || null;
    const hasArchive = !!(current && current.archive);
    const blockedTitle = !state.canGenerate
      ? '本次未选入 2025 年定性解析数据'
      : noSourceMap
        ? '该模板暂不支持自动生成（缺题项映射），请切换到「用户洞察档案」模板'
        : '';

    const genBtn = button('gen');
    if (genBtn) {
      genBtn.disabled = !canGenerate || !state.currentId || noSourceMap || hasArchive;
      genBtn.title = blockedTitle ||
        (hasArchive ? '当前受访者已生成档案；重新生成请用「重新归档当前」，或勾选后批量生成' : '');
    }

    const batchBtn = button('batch');
    if (batchBtn) {
      batchBtn.disabled = !canGenerate || !state.selected.size || noSourceMap;
      batchBtn.textContent = state.selected.size
        ? '批量生成（已勾选 ' + state.selected.size + ' 人）'
        : '批量生成';
      batchBtn.title = blockedTitle ||
        (state.selected.size ? '为勾选的受访者生成档案；已有档案的人自动跳过' : '先在左侧勾选受访者');
    }

    const regen = button('regen');
    if (regen) {
      regen.disabled = !canGenerate || !state.currentId || noSourceMap;
      regen.title = noSourceMap ? '该模板暂不支持自动生成（缺题项映射）' : '';
    }

    const exportBtn = button('export');
    if (exportBtn) {
      exportBtn.disabled = !!state.runId || !state.selected.size;
      exportBtn.textContent = state.selected.size
        ? '导出 Excel（已勾选 ' + state.selected.size + ' 人）'
        : '导出 Excel';
    }

    const mdBtn = button('md');
    if (mdBtn) mdBtn.disabled = !!state.runId || !state.currentId;
    syncSelectAll();
  }

  /* ------------------------------------------------ 绑定 */

  function buildDom() {
    const root = state.root;
    root.innerHTML = '';

    const toolbar = el('div', 'bp-toolbar');
    const scope = el('div', 'bp-scope');
    scope.appendChild(el('span', '', '模板：'));
    const scopeStrong = el('strong', 'bp-scope__template', '加载中…');
    scope.appendChild(scopeStrong);
    scope.appendChild(el('span', 'bp-scope__count', ''));
    toolbar.appendChild(scope);

    const actions = el('div', 'bp-actions');
    const genBtn = el('button', 'bp-btn bp-btn--primary', '生成本人档案');
    genBtn.dataset.bpAction = 'gen';
    const batchBtn = el('button', 'bp-btn', '批量生成');
    batchBtn.dataset.bpAction = 'batch';
    const regen = el('button', 'bp-btn', '重新归档当前');
    regen.dataset.bpAction = 'regen';
    const exportBtn = el('button', 'bp-btn', '导出 Excel');
    exportBtn.dataset.bpAction = 'export';
    const mdBtn = el('button', 'bp-btn', '下载 MD');
    mdBtn.dataset.bpAction = 'md';
    [genBtn, batchBtn, regen, exportBtn, mdBtn].forEach((btn) => actions.appendChild(btn));
    toolbar.appendChild(actions);
    root.appendChild(toolbar);

    const run = el('div', 'bp-run');
    run.hidden = true;
    const runHead = el('div', 'bp-run__head');
    const runRight = el('div', 'bp-run__right');
    const abortBtn = el('button', 'bp-btn bp-btn--small', '中止');
    abortBtn.dataset.bpRunAbort = '1';
    abortBtn.hidden = true;
    const closeBtn = el('button', 'bp-btn bp-btn--small', '关闭');
    closeBtn.dataset.bpRunClose = '1';
    closeBtn.hidden = true;
    runRight.appendChild(el('span', 'bp-run__counts', ''));
    runRight.appendChild(abortBtn);
    runRight.appendChild(closeBtn);
    runHead.appendChild(el('span', 'bp-run__title', ''));
    runHead.appendChild(runRight);
    const runSummary = el('div', 'bp-run__summary');
    runSummary.hidden = true;
    const bar = el('div', 'bp-run__bar');
    bar.appendChild(el('i'));
    run.appendChild(runHead);
    run.appendChild(runSummary);
    run.appendChild(bar);
    run.appendChild(el('ol', 'bp-run__log'));
    root.appendChild(run);
    abortBtn.addEventListener('click', abortRun);
    closeBtn.addEventListener('click', () => {
      run.hidden = true;
      runSummary.hidden = true;
      runSummary.innerHTML = '';
      qs('.bp-run__log', run).innerHTML = '';
      qsa('.bp-alert', state.root).forEach((node) => node.remove());
    });

    const cols = el('div', 'bp-cols');
    const list = el('aside', 'bp-list');
    const head = el('div', 'bp-list__head');
    const title = el('div', 'bp-list__title');
    title.appendChild(document.createTextNode(''));
    title.appendChild(el('span', '', ''));
    head.appendChild(title);
    const selectRow = el('div', 'bp-list__select');
    const selectLabel = el('label');
    const selectAll = document.createElement('input');
    selectAll.type = 'checkbox';
    selectAll.dataset.bpSelectAll = '1';
    selectAll.addEventListener('change', () => {
      const ids = state.respondents.map((row) => row.interview_id);
      if (selectAll.checked) ids.forEach((id) => state.selected.add(id));
      else ids.forEach((id) => state.selected.delete(id));
      renderList();
      updateSelectionUI();
    });
    selectLabel.appendChild(selectAll);
    selectLabel.appendChild(document.createTextNode('全选本页'));
    const selectCount = el('span', '', '');
    selectCount.dataset.bpSelectLabel = '1';
    selectRow.appendChild(selectLabel);
    selectRow.appendChild(selectCount);
    head.appendChild(selectRow);
    const search = el('input', 'bp-search');
    search.placeholder = '搜索编号 / 城市 / 车型';
    search.type = 'search';
    head.appendChild(search);
    list.appendChild(head);
    list.appendChild(el('ul', 'bp-list__items'));
    cols.appendChild(list);

    const doc = el('main', 'bp-doc');
    const docHead = el('div', 'bp-doc__head');
    docHead.appendChild(el('h3', '', '用户洞察档案'));
    docHead.appendChild(el('span', 'bp-doc__meta', ''));
    doc.appendChild(docHead);
    doc.appendChild(el('div', 'bp-doc__body'));

    const quote = el('section', 'bp-quote');
    const quoteHead = el('div', 'bp-quote__head');
    quoteHead.appendChild(document.createTextNode('找原话'));
    quoteHead.appendChild(el('span', '', '按关键词检索答案、证据与标签证据；已勾选受访者时仅查勾选的人（可多选），未勾选时查全部受访者'));
    quote.appendChild(quoteHead);
    const form = el('div', 'bp-quote__form');
    const quoteInput = el('input', 'bp-quote__input');
    quoteInput.placeholder = '输入关键词，例如「空间」「续航」';
    quoteInput.type = 'search';
    const quoteBtn = el('button', 'bp-btn', '搜索');
    form.appendChild(quoteInput);
    form.appendChild(quoteBtn);
    quote.appendChild(form);
    const quoteResults = el('div', 'bp-quote__results');
    quote.appendChild(quoteResults);
    doc.appendChild(quote);
    cols.appendChild(doc);

    root.appendChild(cols);

    // 事件
    const runQuote = async () => {
      const keyword = quoteInput.value.trim();
      if (!keyword) { showAlert('请输入关键词。'); return; }
      quoteResults.innerHTML = '';
      try {
        const params = new URLSearchParams({ keyword: keyword, limit: '50' });
        if (state.selected.size) params.set('interview_id', Array.from(state.selected).join(','));
        const data = await api('/quote?' + params.toString());
        renderQuote(quoteResults, data);
      } catch (err) {
        quoteResults.appendChild(el('div', 'bp-quote__empty', err.message));
      }
    };
    quoteBtn.addEventListener('click', runQuote);
    quoteInput.addEventListener('keydown', (ev) => {
      if (ev.key === 'Enter') { ev.preventDefault(); runQuote(); }
    });

    search.addEventListener('input', debounce(() => {
      state.keyword = search.value.trim();
      loadRespondents()
        .then(() => { renderToolbar(); renderList(); })
        .catch((err) => showAlert(err.message, true));
    }, 250));

    qsa('.bp-btn', actions).forEach((btn) => {
      const action = btn.dataset.bpAction;
      if (action === 'gen') {
        btn.addEventListener('click', () => {
          if (!state.currentId) { showAlert('请先选择一位受访者。'); return; }
          startGenerate([state.currentId], 'single', { force: true });
        });
      } else if (action === 'batch') {
        btn.addEventListener('click', () => {
          if (!state.selected.size) {
            showAlert('请先在左侧勾选受访者，或用「全选本页」。');
            return;
          }
          startGenerate(Array.from(state.selected), 'selected', { force: false, batch: true });
        });
      } else if (action === 'regen') {
        btn.addEventListener('click', () => {
          if (!state.currentId) { showAlert('请先选择一位受访者。'); return; }
          startGenerate([state.currentId], 'single', { force: true });
        });
      } else if (action === 'export') {
        btn.addEventListener('click', exportXlsx);
      } else if (action === 'md') {
        btn.addEventListener('click', exportMd);
      }
    });
    updateActionState();
  }

  function debounce(fn, wait) {
    let timer = null;
    return function debounced() {
      const args = arguments;
      if (timer) clearTimeout(timer);
      timer = setTimeout(() => { timer = null; fn.apply(null, args); }, wait);
    };
  }

  function goDatasource() {
    const tab = qs('[data-bci-tab="datasource"]', document);
    if (tab) tab.click();
  }

  function applyScope(scope) {
    const ds = (scope && scope.datasources) || null;
    const templateId = ds && ds.insight_template;
    if (!templateId) {
      state.canGenerate = false;
      setBlocked('请先在「数据源筛选」中选择洞察档案模板。', '去选择模板', goDatasource);
      return;
    }

    state.canGenerate = ds.interview_parsed === '2025';
    if (state.templateId !== templateId) {
      state.templateId = templateId;
      state.selected = new Set();
      state.currentId = null;
      state.detail = null;
    }
    refresh()
      .then(() => {
        if (!state.canGenerate) {
          showAlert('本次未选入 2025 年定性解析数据，生成按钮已禁用；已有档案仍可查看。');
        }
      })
      .catch((err) => setBlocked('加载失败：' + err.message));
  }

  function setBlocked(message, label, run) {
    const scopeStrong = qs('.bp-scope__template', state.root);
    if (scopeStrong) scopeStrong.textContent = '未选择';
    const count = qs('.bp-scope__count', state.root);
    if (count) count.textContent = '';
    const list = qs('.bp-list__items', state.root);
    if (list) list.innerHTML = '';
    renderBlocked(message, label ? { label: label, run: run } : null);
    updateActionState();
  }

  /* ------------------------------------------------ 生命周期 */

  function init(root) {
    if (state.bound) return;
    state.root = root;
    state.bound = true;
    buildDom();

    const onScope = (ev) => applyScope(ev.detail || readScope());
    document.addEventListener('bci:scope-applied', onScope);
    state._scopeCleanup = () => document.removeEventListener('bci:scope-applied', onScope);

    applyScope(readScope());
  }

  function destroy() {
    if (state.runTimer) { clearInterval(state.runTimer); state.runTimer = null; }
    if (state._scopeCleanup) { state._scopeCleanup(); state._scopeCleanup = null; }
    closePopover();
    state.bound = false;
    state.root = null;
  }

  window.BciProfile = { init: init, destroy: destroy };

  function autoInit() {
    const root = qs('[data-bci-profile]', document);
    if (!root || root.dataset.bpReady) return;
    // 面板未展开时不初始化，由 bci.js 在切到 tab ② 时调用 init。
    if (root.closest('[hidden]')) return;
    root.dataset.bpReady = '1';
    init(root);
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', autoInit);
  } else {
    autoInit();
  }
})();
