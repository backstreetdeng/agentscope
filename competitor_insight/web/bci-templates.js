/**
 * 竞品洞察 · ① 数据源筛选 ·「查看模板」只读弹窗（BCI-002）
 * 归属：competitor_insight/web/bci-templates.js，由 home.html 引入。
 * 数据来源唯一：templates.json 清单 + competitor_insight/templates/*.json 定义，
 * 不复制第二份说明文字；弹窗只读，不写 bci.scope、不改下拉已选值。
 */
(function () {
  'use strict';

  const MANIFEST_URL = '/competitor-insight/templates.json';
  const DEFINITION_PREFIX = '/competitor-insight-templates/';
  const STATUS_TEXT = { ready: '已就绪', pending: '待提供' };

  const qs = (sel, root) => (root || document).querySelector(sel);
  const cache = { manifest: null, definitions: {} };
  let activeId = '';
  let keyword = '';
  let statusFilter = '';

  function el(tag, cls, text) {
    const node = document.createElement(tag);
    if (cls) node.className = cls;
    if (text !== undefined) node.textContent = text;
    return node;
  }

  function definitionName(item) {
    const path = item.definition || '';
    return path.split('/').pop();
  }

  function matches(item) {
    if (statusFilter && item.status !== statusFilter) return false;
    if (!keyword) return true;
    const haystack = [item.label, item.note, item.version,
      STATUS_TEXT[item.status] || item.status, item.id].join(' ').toLowerCase();
    return haystack.indexOf(keyword.toLowerCase()) >= 0;
  }

  function buildShell() {
    const modal = el('div', 'bci-modal');
    modal.setAttribute('data-bci-template-modal', '');
    modal.hidden = true;
    modal.innerHTML = [
      "<div class='bci-modal__mask' data-bci-modal-close></div>",
      "<div class='bci-modal__panel' role='dialog' aria-modal='true' aria-labelledby='bci-modal-title'>",
      "<header class='bci-modal__head'>",
      "<div class='bci-modal__titles'>",
      "<h3 id='bci-modal-title'>洞察档案模板</h3>",
      "<p>内容直接读取模板定义文件，与下拉清单同源。此窗口只读，不改变已选模板。</p>",
      '</div>',
      "<button type='button' class='bci-modal__close' data-bci-modal-close aria-label='关闭'>×</button>",
      '</header>',
      "<div class='bci-modal__body'>",
      "<aside class='bci-tpl-list'>",
      "<input type='search' class='bci-tpl-search' placeholder='按名称 / 类型 / 状态筛选' aria-label='筛选模板' data-bci-tpl-search>",
      "<select class='bci-tpl-status' aria-label='按状态筛选' data-bci-tpl-status>",
      "<option value=''>全部状态</option><option value='ready'>已就绪</option><option value='pending'>待提供</option>",
      '</select>',
      "<div class='bci-tpl-items' data-bci-tpl-items></div>",
      '</aside>',
      "<section class='bci-tpl-detail' data-bci-tpl-detail></section>",
      '</div>',
      '</div>',
    ].join('');
    document.body.appendChild(modal);
    return modal;
  }

  function ensureShell() {
    return qs('[data-bci-template-modal]') || buildShell();
  }

  function renderList(modal) {
    const items = (cache.manifest || []).filter(matches);
    const host = qs('[data-bci-tpl-items]', modal);
    host.innerHTML = '';
    if (!items.length) {
      host.appendChild(el('p', 'bci-tpl-empty', '没有匹配的模板'));
      return;
    }
    items.forEach((item) => {
      const button = el('button', 'bci-tpl-item' + (item.id === activeId ? ' is-active' : ''));
      button.type = 'button';
      button.setAttribute('data-bci-tpl-id', item.id);
      button.appendChild(el('span', 'bci-tpl-item__name', item.label));
      const meta = el('span', 'bci-tpl-item__meta');
      meta.appendChild(el('span', 'bci-tpl-badge bci-tpl-badge--' + item.status,
        STATUS_TEXT[item.status] || item.status));
      if (item.version) meta.appendChild(el('span', 'bci-tpl-item__ver', item.version));
      if (item.note) meta.appendChild(el('span', 'bci-tpl-item__note', item.note));
      button.appendChild(meta);
      host.appendChild(button);
    });
  }

  function renderPending(host, item) {
    host.innerHTML = '';
    const box = el('div', 'bci-tpl-pending');
    box.appendChild(el('span', 'bci-tpl-badge bci-tpl-badge--pending', '待提供'));
    box.appendChild(el('h4', '', item.label));
    box.appendChild(el('p', '', item.reason || item.note || '尚未提供模板文件'));
    host.appendChild(box);
  }

  function renderDefinition(host, item, data) {
    const groups = Array.isArray(data.groups) ? data.groups : [];
    const dims = Array.isArray(data.dimensions) ? data.dimensions : [];
    host.innerHTML = '';

    const head = el('header', 'bci-tpl-head');
    const titleRow = el('div', 'bci-tpl-head__row');
    titleRow.appendChild(el('h4', '', data.name || item.label));
    titleRow.appendChild(el('span', 'bci-tpl-badge bci-tpl-badge--ready', '已就绪'));
    if (data.version) titleRow.appendChild(el('span', 'bci-tpl-item__ver', data.version));
    head.appendChild(titleRow);
    head.appendChild(el('p', 'bci-tpl-head__meta',
      groups.length + ' 组 · ' + dims.length + ' 维 · 必填 ' +
      dims.filter((d) => d.required).length + ' · 选填 ' +
      dims.filter((d) => !d.required).length));
    host.appendChild(head);

    groups.forEach((group) => {
      const block = el('section', 'bci-tpl-group');
      const groupHead = el('div', 'bci-tpl-group__head');
      groupHead.appendChild(el('b', '', group.name));
      if (group.report_section) groupHead.appendChild(el('span', 'bci-tpl-group__tag', group.report_section));
      block.appendChild(groupHead);
      if (group.description) block.appendChild(el('p', 'bci-tpl-group__desc', group.description));

      const rows = dims.filter((d) => d.group === group.id);
      if (!rows.length) {
        block.appendChild(el('p', 'bci-tpl-empty', '该组暂无维度定义'));
      } else {
        const table = el('table', 'bci-tpl-table');
        const thead = el('thead');
        const hr = el('tr');
        ['维度', '必填', '类型', '填写说明', '合格标准'].forEach((t) => hr.appendChild(el('th', '', t)));
        thead.appendChild(hr);
        table.appendChild(thead);
        const tbody = el('tbody');
        rows.forEach((dim) => {
          const tr = el('tr');
          tr.appendChild(el('td', 'bci-tpl-table__dim', dim.name));
          tr.appendChild(el('td', '', dim.required ? '必填' : '选填'));
          tr.appendChild(el('td', '', dim.type || '—'));
          tr.appendChild(el('td', '', dim.description || '—'));
          tr.appendChild(el('td', '', dim.qualified || '—'));
          tbody.appendChild(tr);
        });
        table.appendChild(tbody);
        block.appendChild(table);
      }
      host.appendChild(block);
    });
  }

  async function showDefinition(modal, item) {
    const host = qs('[data-bci-tpl-detail]', modal);
    activeId = item.id;
    renderList(modal);
    if (item.status === 'pending' || !item.definition) {
      renderPending(host, item);
      return;
    }
    host.innerHTML = "<p class='bci-tpl-empty'>正在读取模板定义…</p>";
    try {
      if (!cache.definitions[item.id]) {
        const response = await fetch(DEFINITION_PREFIX + definitionName(item));
        if (!response.ok) throw new Error('HTTP ' + response.status);
        cache.definitions[item.id] = await response.json();
      }
      if (activeId !== item.id) return;
      renderDefinition(host, item, cache.definitions[item.id]);
    } catch (error) {
      if (activeId !== item.id) return;
      host.innerHTML = '';
      const box = el('div', 'bci-tpl-pending');
      box.appendChild(el('h4', '', '模板定义读取失败'));
      box.appendChild(el('p', '', String(error && error.message ? error.message : error)));
      host.appendChild(box);
    }
  }

  async function openModal() {
    const modal = ensureShell();
    modal.hidden = false;
    document.body.classList.add('bci-modal-open');
    const closeBtn = qs('.bci-modal__close', modal);
    if (closeBtn) closeBtn.focus();
    if (!cache.manifest) {
      qs('[data-bci-tpl-items]', modal).innerHTML = "<p class='bci-tpl-empty'>正在读取模板清单…</p>";
      try {
        const response = await fetch(MANIFEST_URL);
        if (!response.ok) throw new Error('HTTP ' + response.status);
        const manifest = await response.json();
        cache.manifest = Array.isArray(manifest.templates) ? manifest.templates : [];
      } catch (error) {
        qs('[data-bci-tpl-items]', modal).innerHTML =
          "<p class='bci-tpl-empty'>模板清单读取失败：" + String(error && error.message ? error.message : error) + '</p>';
        return;
      }
    }
    const items = cache.manifest;
    const target = items.filter((item) => item.id === activeId)[0] || items[0];
    renderList(modal);
    if (target) await showDefinition(modal, target);
  }

  function closeModal() {
    const modal = qs('[data-bci-template-modal]');
    if (!modal) return;
    modal.hidden = true;
    document.body.classList.remove('bci-modal-open');
  }

  document.addEventListener('click', (event) => {
    const opener = event.target.closest('[data-bci-template-view]');
    if (opener) {
      event.preventDefault();
      openModal();
      return;
    }
    const closer = event.target.closest('[data-bci-modal-close]');
    if (closer) {
      event.preventDefault();
      closeModal();
      return;
    }
    const item = event.target.closest('[data-bci-tpl-id]');
    if (item) {
      const modal = qs('[data-bci-template-modal]');
      const found = (cache.manifest || []).filter((t) => t.id === item.getAttribute('data-bci-tpl-id'))[0];
      if (modal && found) showDefinition(modal, found);
    }
  });

  document.addEventListener('input', (event) => {
    if (!event.target.matches('[data-bci-tpl-search]')) return;
    const modal = qs('[data-bci-template-modal]');
    keyword = event.target.value.trim();
    if (modal) renderList(modal);
  });

  document.addEventListener('change', (event) => {
    if (!event.target.matches('[data-bci-tpl-status]')) return;
    const modal = qs('[data-bci-template-modal]');
    statusFilter = event.target.value;
    if (modal) renderList(modal);
  });

  document.addEventListener('keydown', (event) => {
    if (event.key !== 'Escape') return;
    const modal = qs('[data-bci-template-modal]');
    if (modal && !modal.hidden) {
      event.preventDefault();
      closeModal();
    }
  });
})();
