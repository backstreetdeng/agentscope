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
    const btn = el('button', 'bp-btn bp-btn--primary', '生成本人档案');
    btn.addEventListener('click', () => {
      if (!state.currentId) return;
      if (!state.canGenerate) { showAlert('本次未选入 2025 年定性解析数据，暂不能生成。'); return; }
      startGenerate([state.currentId], 'single');
    });
    empty.appendChild(btn);
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
  }

  function updateSelectionUI() {
    const title = qs('.bp-list__title', state.root);
    if (title && title.childNodes[1]) title.childNodes[1].textContent = ' · 已勾选 ' + state.selected.size;
    const count = qs('[data-bp-export-count]', state.root);
    if (count) count.textContent = state.selected.size ? '导出 Excel（已勾选 ' + state.selected.size + ' 人）' : '导出 Excel';
    qsa('.bp-item', state.root).forEach((li) => {
      const cb = qs('input[type="checkbox"]', li);
      li.classList.toggle('is-selected', cb.checked);
    });
    updateActionState();
  }

  /* ------------------------------------------------ 渲染：档案表 */

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
    (state.template.groups || []).forEach((g) => { groups[g.id] = g.name || g.id; });
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
      const dimCell = el('td', 'bp-cell--dim', dim.name || dim.id);
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
    return found ? (found.name || id) : id;
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

  async function startGenerate(ids, mode) {
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
          force: true,
        }),
      });
      state.runId = payload.run_id;
      updateActionState();
      showRunPanel(payload);
      pollRun();
    } catch (err) {
      if (err.code === 'run_in_progress') {
        state.runId = err.payload.run_id;
        updateActionState();
        pollRun();
      } else {
        showAlert(err.message, true);
      }
    }
  }

  function showRunPanel(payload) {
    const panel = qs('.bp-run', state.root);
    panel.hidden = false;
    const head = qs('.bp-run__head', panel);
    head.childNodes[0].textContent = '';
    head.childNodes[0].appendChild(document.createTextNode('正在归档'));
    head.childNodes[0].appendChild(el('span', '', '（' + payload.total + ' 人）'));
    const log = qs('.bp-run__log', panel);
    log.innerHTML = '';
    (payload.skipped ? [{ interview_id: '-', status: 'skipped', error: '已有 ready 档案，跳过 ' + payload.skipped + ' 人' }] : []).forEach((item) => {
      log.appendChild(logLine(item));
    });
  }

  function logLine(item) {
    const li = document.createElement('li');
    li.className = 'is-' + (item.status || 'running');
    const code = item.interview_id === '-' ? '系统' : (item.interview_id || '');
    li.appendChild(el('span', '', code));
    const label = { done: '完成', failed: '失败', running: '生成中', skipped: '跳过' }[item.status] || item.status;
    li.appendChild(el('span', '', label + (item.error ? '：' + item.error : '')));
    return li;
  }

  function pollRun() {
    if (!state.runId) return;
    const tick = async () => {
      try {
        const data = await api('/run?run_id=' + encodeURIComponent(state.runId));
        const panel = qs('.bp-run', state.root);
        panel.hidden = false;
        const bar = qs('.bp-run__bar i', panel);
        bar.style.width = data.progress + '%';
        const head = qs('.bp-run__head', panel);
        head.childNodes[0].textContent = '';
        head.childNodes[0].appendChild(document.createTextNode(runTitle(data)));
        head.childNodes[0].appendChild(el('span', '', '（' + data.done + ' 完成 · ' + data.failed + ' 失败）'));
        const log = qs('.bp-run__log', panel);
        log.innerHTML = '';
        (data.items || []).forEach((item) => log.appendChild(logLine(item)));

        if (data.status === 'completed' || data.status === 'partial' || data.status === 'failed') {
          state.runId = null;
          if (state.runTimer) { clearInterval(state.runTimer); state.runTimer = null; }
          updateActionState();
          showAlert(runResultMessage(data));
          await refresh();
          setTimeout(() => { panel.hidden = true; }, 1500);
        }
      } catch (err) {
        if (state.runTimer) { clearInterval(state.runTimer); state.runTimer = null; }
        state.runId = null;
        updateActionState();
        showAlert(err.message, true);
      }
    };
    if (state.runTimer) clearInterval(state.runTimer);
    tick();
    state.runTimer = setInterval(tick, 1500);
  }

  function runTitle(data) {
    const map = {
      queued: '排队中', running: '正在归档', completed: '归档完成',
      partial: '部分完成', failed: '失败', cancelled: '已取消',
    };
    return map[data.status] || data.status;
  }

  function runResultMessage(data) {
    if (data.status === 'completed') return '归档完成：' + data.done + ' 人全部生成。';
    if (data.status === 'partial') return '部分完成：' + data.done + ' 人成功，' + data.failed + ' 人失败（详情见运行日志）。';
    return '归档失败：' + (data.error_text || '未知原因') + '。';
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
    const buttons = qsa('.bp-btn', actions);
    const canGenerate = state.canGenerate && !!state.template && !state.runId;
    if (buttons[0]) {
      buttons[0].disabled = !canGenerate || !state.currentId;
      buttons[0].title = state.canGenerate ? '' : '本次未选入 2025 年定性解析数据';
    }
    if (buttons[1]) buttons[1].disabled = !canGenerate || !state.currentId;
    if (buttons[2]) buttons[2].disabled = !!state.runId || !state.selected.size;
    if (buttons[3]) buttons[3].disabled = !!state.runId || !state.currentId;
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
    actions.appendChild(el('button', 'bp-btn', '生成本人档案'));
    const regen = el('button', 'bp-btn', '重新归档当前');
    actions.appendChild(regen);
    const exportBtn = el('button', 'bp-btn bp-btn--primary', '导出 Excel');
    exportBtn.dataset.bpExportCount = '1';
    actions.appendChild(exportBtn);
    actions.appendChild(el('button', 'bp-btn', '下载 MD'));
    toolbar.appendChild(actions);
    root.appendChild(toolbar);

    const run = el('div', 'bp-run');
    run.hidden = true;
    const runHead = el('div', 'bp-run__head');
    runHead.appendChild(el('span', '', ''));
    const bar = el('div', 'bp-run__bar');
    bar.appendChild(el('i'));
    run.appendChild(runHead);
    run.appendChild(bar);
    run.appendChild(el('ol', 'bp-run__log'));
    root.appendChild(run);

    const cols = el('div', 'bp-cols');
    const list = el('aside', 'bp-list');
    const head = el('div', 'bp-list__head');
    const title = el('div', 'bp-list__title');
    title.appendChild(document.createTextNode(''));
    title.appendChild(el('span', '', ''));
    head.appendChild(title);
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
    quoteHead.appendChild(el('span', '', '按关键词检索答案、证据、标签证据与当前档案值'));
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
      if (!state.currentId) { showAlert('请先选择一位受访者。'); return; }
      if (!keyword) { showAlert('请输入关键词。'); return; }
      quoteResults.innerHTML = '';
      try {
        const data = await api(
          '/quote?interview_id=' + encodeURIComponent(state.currentId) +
          '&keyword=' + encodeURIComponent(keyword) + '&limit=50'
        );
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
      if (btn === regen) {
        btn.addEventListener('click', () => {
          if (!state.currentId) { showAlert('请先选择一位受访者。'); return; }
          startGenerate([state.currentId], 'single');
        });
      } else if (btn === exportBtn) {
        btn.addEventListener('click', exportXlsx);
      } else if (btn.textContent === '下载 MD') {
        btn.addEventListener('click', exportMd);
      } else if (btn.textContent === '生成本人档案') {
        btn.addEventListener('click', () => {
          if (!state.currentId) { showAlert('请先选择一位受访者。'); return; }
          startGenerate([state.currentId], 'single');
        });
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
