/*!
 * 竞品洞察 · ① 数据源筛选（BCI-001）
 * 归属：competitor_insight/web/bci.js，由 home.html 引入，经 /competitor-insight/ 静态路由提供。
 * 模块自包含（不依赖 home.js 的私有工具函数），只向 window 暴露 BciWorkspace。
 */
(function () {
  'use strict';

  const qs = (sel, root) => (root || document).querySelector(sel);
  const qsa = (sel, root) => Array.from((root || document).querySelectorAll(sel));
  const on = (target, type, handler) => { if (target) target.addEventListener(type, handler); };

  // ────────────────────────────────────────────────────────────────────────
  //  BCI 竞品洞察 · ① 数据源筛选
  //  前提是后台已完成标准化数据与洞察档案模板的接入；本页只做「为本次分析
  //  选择数据源与模板」。四类默认都不选，不选即该类数据不参与后续洞察。
  //  选项与可用性为 2026-11-06 的核对结果，依据见
  //  competitor_insight/tasks/BCI-001/TASK.md 第 5 节。
  // ────────────────────────────────────────────────────────────────────────
  const BciWorkspace = (() => {
    const STORAGE_KEY = 'bci.scope';
    const VERSION = 2;

    const GROUPS = [
      {
        key: 'quant_structured',
        title: '定量结构化数据',
        desc: '三个年度可单选也可多选；未选中的年度不参与本次分析。',
        multi: true,
        options: [
          { value: '2023', label: '2023 年', note: '959 份 · 851 个题项' },
          { value: '2024', label: '2024 年', note: '2,094 份 · 1,042 个题项' },
          { value: '2025', label: '2025 年', note: '1,380 份 · 1,324 个题项 · 已入库' },
        ],
      },
      {
        key: 'interview_parsed',
        title: '定性深访解析数据',
        desc: '当前只有 2025 年完成解析；未解析的年度不可选。',
        multi: false,
        options: [
          { value: '2025', label: '2025年_定性解析', note: '63 人' },
          {
            value: '2026',
            label: '2026年_定性解析',
            note: '音频尚未解析',
            available: false,
            reason: '2026 年深访音频尚未转写解析，暂不可选',
          },
        ],
      },
      {
        key: 'insight_template',
        title: '深访用户洞察档案模板',
        desc: '决定后续档案按哪套章节结构生成；模板清单由 templates.json 提供。',
        multi: false,
        // 选项不写死：进入视图时从清单读取，新增模板只改清单与模板定义文件。
        options: [],
        templatesUrl: '/competitor-insight/templates.json',
      },
      {
        key: 'flow_data',
        title: '流通数据（增换购流转分析）',
        desc: '用于用户来源与流转结构分析；数据尚未提供。',
        multi: false,
        options: [
          {
            value: 'enabled',
            label: '增换购流转分析',
            note: '待业务提供',
            available: false,
            reason: '业务数据尚未提供，暂不可选',
          },
        ],
      },
    ];

    const EMPTY = {
      quant_structured: [],
      interview_parsed: '',
      insight_template: '',
      flow_data: '',
    };

    const state = {
      selected: Object.assign({}, EMPTY, { quant_structured: [] }),
      bound: false,
      ready: false,
      savedAt: '',
    };

    function viewRoot() { return qs(".view[data-view='bci']"); }

    function groupOf(key) { return GROUPS.find((g) => g.key === key); }

    function buildScope() {
      return {
        version: VERSION,
        datasources: {
          quant_structured: state.selected.quant_structured.slice(),
          interview_parsed: state.selected.interview_parsed,
          insight_template: state.selected.insight_template,
          flow_data: state.selected.flow_data,
        },
      };
    }

    function activeCount() {
      let n = 0;
      GROUPS.forEach((g) => {
        const v = state.selected[g.key];
        if (g.multi ? v.length > 0 : !!v) n += 1;
      });
      return n;
    }

    function valueText(group) {
      const value = state.selected[group.key];
      if (group.multi) {
        if (!value.length) return '不选';
        return value.map((v) => {
          const opt = group.options.find((o) => o.value === v);
          return opt ? opt.label.replace(' 年', '') : v;
        }).join('、');
      }
      if (!value) return '不选';
      const opt = group.options.find((o) => o.value === value);
      return opt ? opt.label : value;
    }

    // 模板清单：由 /competitor-insight/templates.json 提供，前端不再写死选项。
    // status=ready 才可选；pending 项自动 disabled 并展示 reason。
    function templateOptionsFrom(manifest) {
      const list = manifest && Array.isArray(manifest.templates) ? manifest.templates : [];
      return list.filter((t) => t && t.id).map((t) => {
        const ready = t.status === 'ready';
        const version = t.version ? t.version + ' · ' : '';
        return {
          value: t.id,
          label: t.label || t.name || t.id,
          note: version + (t.note || (ready ? '可用' : '待提供')),
          available: ready,
          reason: ready ? '' : (t.reason || '业务尚未提供该模板'),
        };
      });
    }

    function loadTemplates() {
      const group = groupOf('insight_template');
      if (!group || !group.templatesUrl) return Promise.resolve(false);
      return fetch(group.templatesUrl, { cache: 'no-store' })
        .then((res) => {
          if (!res.ok) throw new Error('HTTP ' + res.status);
          return res.json();
        })
        .then((manifest) => {
          const options = templateOptionsFrom(manifest);
          if (!options.length) throw new Error('模板清单为空');
          group.options = options;
          return true;
        })
        .catch(() => {
          // 加载失败时不伪造正常清单：只留一条不可选项，说明本次不选模板。
          group.options = [{
            value: '__template_manifest_unavailable__',
            label: '模板清单加载失败',
            note: '不可选',
            available: false,
            reason: '未能读取 templates.json，请刷新页面重试；本次不选模板',
          }];
          return false;
        });
    }

    function renderGroups() {
      const host = qs('#bci-groups', viewRoot());
      if (!host) return;
      host.innerHTML = GROUPS.map((group, index) => {
        const options = (group.multi ? [] : [{ value: '', label: '不选', note: '该类数据不参与本次洞察' }])
          .concat(group.options);
        const rows = options.map((opt) => {
          const disabled = opt.available === false;
          const inputType = group.multi ? 'checkbox' : 'radio';
          const checkedAttr = group.multi
            ? (state.selected[group.key].indexOf(opt.value) >= 0 ? ' checked' : '')
            : (state.selected[group.key] === opt.value ? ' checked' : '');
          const reason = disabled && opt.reason
            ? "<span class='bci-option__reason'>" + opt.reason + '</span>' : '';
          return [
            "<label class='bci-option" + (disabled ? ' is-disabled' : '') + "' data-bci-value='" + opt.value + "'>",
            "<input type='" + inputType + "' name='bci-" + group.key + "' value='" + opt.value + "'" +
              checkedAttr + (disabled ? ' disabled' : '') + '>',
            "<span class='bci-option__body'>",
            "<span class='bci-option__label'>" + opt.label + '</span>',
            opt.note ? "<span class='bci-option__note'>" + opt.note + '</span>' : '',
            reason,
            '</span>',
            '</label>',
          ].join('');
        }).join('');
        return [
          "<section class='bci-block'>",
          "<header class='bci-block__head'>",
          "<h4 class='bci-block__title'><span class='bci-block__step'>" + (index + 1) + '</span>' + group.title + '</h4>',
          "<p class='bci-block__desc'>" + group.desc + '</p>',
          '</header>',
          "<div class='bci-select' data-bci-group='" + group.key + "'>",
          "<button type='button' class='bci-select__btn' aria-haspopup='true' aria-expanded='false'>",
          "<span class='bci-select__value'></span>",
          "<svg class='bci-select__caret' width='12' height='12' viewBox='0 0 12 12' aria-hidden='true'>" +
            "<path d='M2.5 4.5 6 8l3.5-3.5' fill='none' stroke='currentColor' stroke-width='1.6' " +
            "stroke-linecap='round' stroke-linejoin='round'/></svg>",
          '</button>',
          "<div class='bci-select__panel' role='group' hidden>" + rows + '</div>',
          '</div>',
          '</section>',
        ].join('');
      }).join('');
      refreshLabels();
    }

    function refreshLabels() {
      qsa('.bci-select', viewRoot()).forEach((box) => {
        const group = groupOf(box.getAttribute('data-bci-group'));
        if (!group) return;
        const text = valueText(group);
        const target = qs('.bci-select__value', box);
        if (target) target.textContent = text;
        box.classList.toggle('has-value', text !== '不选');
        box.classList.toggle('is-partial', !!group.multi && state.selected[group.key].length === 0);
      });
    }

    function renderScopeText() {
      const el = qs('#bci-scope-text');
      if (!el) return;
      const parts = [];
      GROUPS.forEach((group) => {
        const value = state.selected[group.key];
        const filled = group.multi ? value.length > 0 : !!value;
        if (filled) parts.push(group.title.replace(/（.*?）/g, '') + ' ' + valueText(group));
      });
      el.textContent = parts.length ? '已选 ' + parts.length + ' 类 · ' + parts.join(' · ') : '全部不选';
    }

    function renderPreview() {
      const pre = qs('#bci-scope-preview');
      if (pre) pre.textContent = JSON.stringify(buildScope(), null, 2);
      const foot = qs('#bci-scope-status');
      if (foot) {
        foot.textContent = state.savedAt
          ? '已写入 ' + STORAGE_KEY + ' · ' + state.savedAt + ' · 本次共选 ' + activeCount() + ' 类'
          : '尚未选择，四类数据均不参与';
      }
      renderScopeText();
    }

    function stamp() {
      const now = new Date();
      const pad = (n) => (n < 10 ? '0' + n : String(n));
      return now.getFullYear() + '-' + pad(now.getMonth() + 1) + '-' + pad(now.getDate()) +
        ' ' + pad(now.getHours()) + ':' + pad(now.getMinutes());
    }

    function persist() {
      const scope = buildScope();
      state.savedAt = stamp();
      try {
        localStorage.setItem(STORAGE_KEY, JSON.stringify(scope));
      } catch (error) { /* 存储不可用时仍保留内存态 */ }
      window.BCI_SCOPE = scope;
      document.dispatchEvent(new CustomEvent('bci:scope-applied', { detail: scope }));
      renderPreview();
    }

    function closePanels(except) {
      qsa('.bci-select', viewRoot()).forEach((box) => {
        if (except && box === except) return;
        box.classList.remove('is-open');
        box.setAttribute('aria-expanded', 'false');
        const panel = qs('.bci-select__panel', box);
        if (panel) panel.hidden = true;
      });
    }

    function togglePanel(box) {
      const panel = qs('.bci-select__panel', box);
      if (!panel) return;
      const open = panel.hidden;
      closePanels(box);
      panel.hidden = !open;
      box.classList.toggle('is-open', open);
      box.setAttribute('aria-expanded', open ? 'true' : 'false');
    }

    function onChange(input) {
      const box = input.closest('.bci-select');
      if (!box) return;
      const group = groupOf(box.getAttribute('data-bci-group'));
      if (!group) return;
      if (group.multi) {
        const next = state.selected[group.key].filter((v) => v !== input.value);
        if (input.checked) next.push(input.value);
        state.selected[group.key] = group.options
          .map((o) => o.value)
          .filter((v) => next.indexOf(v) >= 0);
      } else {
        state.selected[group.key] = input.value;
      }
      refreshLabels();
      persist();
    }

    function resetAll() {
      state.selected = Object.assign({}, EMPTY, { quant_structured: [] });
      try { localStorage.removeItem(STORAGE_KEY); } catch (error) { /* ignore */ }
      window.BCI_SCOPE = buildScope();
      state.savedAt = '';
      qsa('.bci-select input', viewRoot()).forEach((input) => { input.checked = false; });
      refreshLabels();
      renderPreview();
      document.dispatchEvent(new CustomEvent('bci:scope-applied', { detail: window.BCI_SCOPE }));
    }

    function restore() {
      let stored = null;
      try {
        stored = JSON.parse(localStorage.getItem(STORAGE_KEY) || 'null');
      } catch (error) { stored = null; }
      if (!stored || !stored.datasources) return;
      GROUPS.forEach((group) => {
        const allowed = group.options.map((o) => o.value);
        const value = stored.datasources[group.key];
        if (group.multi) {
          if (Array.isArray(value)) {
            state.selected[group.key] = allowed.filter((v) => value.indexOf(v) >= 0);
          }
        } else if (allowed.indexOf(value) >= 0) {
          state.selected[group.key] = value;
        }
      });
      state.savedAt = '上次保存';
    }

    function bind() {
      if (state.bound) return;
      const root = viewRoot();
      if (!root) return;
      state.bound = true;

      on(root, 'click', (ev) => {
        const btn = ev.target.closest('.bci-select__btn');
        if (btn) {
          ev.preventDefault();
          togglePanel(btn.closest('.bci-select'));
          return;
        }
        if (!ev.target.closest('.bci-select')) closePanels(null);

        const reset = ev.target.closest('#bci-reset');
        if (reset) resetAll();

        const tab = ev.target.closest('[data-bci-tab]');
        if (tab && !tab.disabled) {
          const key = tab.getAttribute('data-bci-tab');
          qsa('[data-bci-tab]', root).forEach((t) => {
            const on = t === tab;
            t.classList.toggle('is-active', on);
            t.setAttribute('aria-selected', on ? 'true' : 'false');
          });
          qsa('[data-bci-panel]', root).forEach((p) => {
            p.hidden = p.getAttribute('data-bci-panel') !== key;
          });
          if (key === 'profile') initProfile(root);
          if (key === 'analyze') initAnalysis(root);
        }
      });

      on(root, 'change', (ev) => {
        if (ev.target.closest('.bci-option')) onChange(ev.target);
      });

      on(document, 'keydown', (ev) => {
        if (ev.key === 'Escape') closePanels(null);
      });
    }

    // tab ② 首次进入时才初始化档案模块，避免首页加载即查询数据库。
    function initProfile(root) {
      const host = qs('[data-bci-profile]', root);
      if (host && window.BciProfile) window.BciProfile.init(host);
    }

    // tab ③ 首次进入时才初始化即时分析，避免首页加载即查询四类数据源。
    function initAnalysis(root) {
      const host = qs('[data-bci-analysis]', root);
      if (host && window.BciAnalysis) window.BciAnalysis.init(host);
    }

    let entering = null;

    function enter() {
      bind();
      if (state.ready) return Promise.resolve();
      if (entering) return entering;
      // 先拿模板清单再 restore：restore() 按当前 options 过滤已存值，
      // 顺序颠倒会把上次选中的模板丢掉。
      entering = loadTemplates().then(() => {
        restore();
        renderGroups();
        renderPreview();
        window.BCI_SCOPE = buildScope();
        state.ready = true;
        entering = null;
      });
      return entering;
    }

    function init() {
      document.addEventListener('view:enter', (ev) => {
        if (ev && ev.detail && ev.detail.view === 'bci') enter();
      });
      const root = viewRoot();
      if (root && !root.hidden) enter();
    }

    return { init, enter };
  })();

  window.BciWorkspace = BciWorkspace;
})();
