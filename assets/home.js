/*!
 * Strategy Cockpit — Home page interactions
 * B2B SaaS dashboard for 乘用车市场战略决策AI智能体系统
 * (Passenger-car Market Strategy Decision AI Agent System)
 * IIFE module, no global pollution; exports a small surface on window.Home.
 */
(function () {
  'use strict';

  // ────────────────────────────────────────────────────────────────────────
  //  Configuration & constants
  // ────────────────────────────────────────────────────────────────────────
  const CONFIG = Object.freeze({
    HEALTH_INTERVAL_MS: 30000,
    HEALTH_ENDPOINT: '/api/health',
    COUNTER_DURATION_MS: 1200,
    PULSE_INTERVAL_MS: 1000,
    TOAST_TTL_MS: 3000,
    MOBILE_BREAKPOINT: 960,
    VIEW_TRANSITION_MS: 150,
    MAIN_NAV_KEYS: ['intel', 'projects', 'analysis', 'forecast', 'insight', 'skills', 'plugins'],
    LEGACY_WORKBENCH: '/legacy/workbench.html',
  });

  // ────────────────────────────────────────────────────────────────────────
  //  Tiny utility belt
  // ────────────────────────────────────────────────────────────────────────
  const utils = {
    qs(sel, root) { return (root || document).querySelector(sel); },
    qsa(sel, root) { return Array.from((root || document).querySelectorAll(sel)); },
    on(target, type, handler, opts) {
      if (!target) return () => {};
      target.addEventListener(type, handler, opts || false);
      return () => target.removeEventListener(type, handler, opts || false);
    },

    // Throttle: leading + trailing, fixed window.
    throttle(fn, wait) {
      let last = 0;
      let timer = null;
      let lastArgs = null;
      return function throttled(...args) {
        const now = Date.now();
        const remaining = wait - (now - last);
        if (remaining <= 0) {
          if (timer) { clearTimeout(timer); timer = null; }
          last = now;
          fn.apply(this, args);
        } else {
          lastArgs = args;
          if (!timer) {
            timer = setTimeout(() => {
              last = Date.now();
              timer = null;
              if (lastArgs) { fn.apply(this, lastArgs); lastArgs = null; }
            }, remaining);
          }
        }
      };
    },

    debounce(fn, wait) {
      let timer = null;
      return function debounced(...args) {
        if (timer) clearTimeout(timer);
        timer = setTimeout(() => fn.apply(this, args), wait);
      };
    },

    easeOutCubic(t) { return 1 - Math.pow(1 - t, 3); },

    formatThousands(n) {
      const v = Math.round(n);
      try {
        return v.toLocaleString('en-US');
      } catch (e) {
        return String(v).replace(/\B(?=(\d{3})+(?!\d))/g, ',');
      }
    },

    isMobileViewport() {
      return window.matchMedia && window.matchMedia('(max-width: ' + CONFIG.MOBILE_BREAKPOINT + 'px)').matches;
    },

    isVisible(el) {
      if (!el) return false;
      if (el.hidden) return false;
      const style = window.getComputedStyle(el);
      return style.display !== 'none' && style.visibility !== 'hidden';
    },

    idleCallback(fn, opts) {
      if (typeof window.requestIdleCallback === 'function') {
        return window.requestIdleCallback(fn, opts || { timeout: 1500 });
      }
      return setTimeout(fn, 0);
    },

    cancelIdle(id) {
      if (typeof window.cancelIdleCallback === 'function') return window.cancelIdleCallback(id);
      clearTimeout(id);
    },
  };

  // ────────────────────────────────────────────────────────────────────────
  //  Reduced-motion detection
  // ────────────────────────────────────────────────────────────────────────
  const ReducedMotion = (() => {
    let mql = null;
    let enabled = false;
    function refresh() {
      enabled = !!(mql && mql.matches);
      document.documentElement.setAttribute('data-reduced-motion', enabled ? 'true' : 'false');
    }
    
  // ────────────────────────────────────────────────────────────────────────
  //  KouBei Integration — 懂车帝口碑平台数据集成
  //  Fetches /api/dashboard from port 8765 and updates the WOM card.
  //  Gracefully falls back to static values when platform is offline.
  // ────────────────────────────────────────────────────────────────────────
  const KouBei = (() => {
    const KOUBEI_BASE = 'http://127.0.0.1:8765';
    const TIMEOUT_MS = 5000;

    function setText(id, val) {
      const el = utils.qs('#' + id);
      if (el) el.textContent = val;
    }

    function formatNumber(n) {
      if (typeof n !== 'number' || isNaN(n)) return String(n);
      return n.toLocaleString('en-US');
    }

    async function fetchDashboard() {
      try {
        const controller = new AbortController();
        const timer = setTimeout(() => controller.abort(), TIMEOUT_MS);
        const res = await fetch(KOUBEI_BASE + '/api/dashboard', { signal: controller.signal });
        clearTimeout(timer);
        if (!res.ok) throw new Error('HTTP ' + res.status);
        const data = await res.json();
        return data;
      } catch (e) {
        return null;
      }
    }

    function updateCard(data) {
      if (!data || !data.stats) return;
      const s = data.stats;
      setText('koubei-total', formatNumber(s.koubei_total || 9631));
      setText('koubei-series', formatNumber(s.matched_total || 107));
      setText('koubei-matched', formatNumber(s.matched_total || 107));
      if (s.latest_posttime) {
        setText('koubei-latest-date', s.latest_posttime.substring(0, 10));
      }
    }

    function init() {
      // Delay to not block initial render
      if (typeof requestIdleCallback === 'function') {
        requestIdleCallback(async () => {
          const data = await fetchDashboard();
          if (data) updateCard(data);
        });
      } else {
        setTimeout(async () => {
          const data = await fetchDashboard();
          if (data) updateCard(data);
        }, 1500);
      }
    }

    return { init };
  })();

  // ────────────────────────────────────────────────────────────────────────

  function init() {
      mql = window.matchMedia ? window.matchMedia('(prefers-reduced-motion: reduce)') : null;
      if (!mql) { enabled = false; return; }
      enabled = mql.matches;
      document.documentElement.setAttribute('data-reduced-motion', enabled ? 'true' : 'false');
      if (mql.addEventListener) mql.addEventListener('change', refresh);
      else if (mql.addListener) mql.addListener(refresh);
    }
    return {
      init,
      get enabled() { return enabled; },
    };
  })();

  // ────────────────────────────────────────────────────────────────────────
  //  Toast component (aria-live="polite", top-right)
  // ────────────────────────────────────────────────────────────────────────
  const Toast = (() => {
    const TYPE_CLASS = { info: 'toast--info', success: 'toast--success', warn: 'toast--warn', error: 'toast--error' };
    let host = null;

    function ensureHost() {
      if (host) return host;
      host = document.createElement('div');
      host.className = 'toast-host';
      host.setAttribute('aria-live', 'polite');
      host.setAttribute('aria-atomic', 'true');
      host.dataset.role = 'status';
      Object.assign(host.style, {
        position: 'fixed', top: '20px', right: '20px', zIndex: '9999',
        display: 'flex', flexDirection: 'column', gap: '10px',
        pointerEvents: 'none', maxWidth: '320px',
      });
      document.body.appendChild(host);
      return host;
    }

    function show(message, type) {
      const kind = TYPE_CLASS[type] ? type : 'info';
      const node = document.createElement('div');
      node.className = 'toast toast--enter ' + TYPE_CLASS[kind];
      node.setAttribute('role', kind === 'error' ? 'alert' : 'status');
      node.textContent = String(message == null ? '' : message);
      Object.assign(node.style, {
        pointerEvents: 'auto',
        padding: '10px 14px',
        borderRadius: '10px',
        boxShadow: '0 8px 24px rgba(0,0,0,0.18)',
        fontSize: '13px',
        lineHeight: '1.4',
        opacity: '0',
        transform: 'translateY(-6px)',
        transition: 'opacity 180ms ease, transform 180ms ease',
        color: '#f9fafb',
      });
      const tint = {
        info: 'linear-gradient(135deg, #2563eb, #1d4ed8)',
        success: 'linear-gradient(135deg, #059669, #047857)',
        warn: 'linear-gradient(135deg, #d97706, #b45309)',
        error: 'linear-gradient(135deg, #dc2626, #b91c1c)',
      }[kind];
      node.style.background = tint;

      ensureHost().appendChild(node);
      requestAnimationFrame(() => {
        node.style.opacity = '1';
        node.style.transform = 'translateY(0)';
      });

      setTimeout(() => {
        node.style.opacity = '0';
        node.style.transform = 'translateY(-6px)';
        setTimeout(() => { if (node.parentNode) node.parentNode.removeChild(node); }, 220);
      }, CONFIG.TOAST_TTL_MS);
    }

    return { show };
  })();

  // ────────────────────────────────────────────────────────────────────────
  //  Sidebar & view navigation
  // ────────────────────────────────────────────────────────────────────────
  const Navigation = (() => {
    const state = { currentView: 'intel' };
    let apiCache = null;

    function getMainNavItems() {
      return utils.qsa('.sidebar .nav-section:not([data-section="history"]) .nav-item[data-view]')
        .filter((n) => CONFIG.MAIN_NAV_KEYS.includes(n.dataset.view));
    }

    function setActive(view) {
      state.currentView = view;
      utils.qsa('.nav-item[data-view]').forEach((item) => {
        const isActive = item.dataset.view === view;
        item.classList.toggle('is-active', isActive);
        if (isActive) item.setAttribute('aria-current', 'page');
        else item.removeAttribute('aria-current');
      });

      utils.qsa('.view[data-view]').forEach((v) => {
        const match = v.dataset.view === view;
        if (match) {
          v.hidden = false;
          v.classList.add('is-visible');
        } else {
          v.hidden = true;
          v.classList.remove('is-visible');
        }
      });

      const titleEl = utils.qs('#active-view-title');
      const active = utils.qs('.nav-item[data-view="' + view + '"] .nav-label');
      if (titleEl) titleEl.textContent = active ? active.textContent.trim() : view;

      try {
        document.dispatchEvent(new CustomEvent('view:enter', { detail: { view } }));
      } catch (e) { /* ignore */ }
    }

    function switchTo(view) {
      if (!view) return;
      if (state.currentView === view) return;
      setActive(view);
      if (utils.isMobileViewport()) closeSidebar();
    }

    function toggleSidebar(force) {
      const sb = utils.qs('.sidebar');
      if (!sb) return;
      const willOpen = typeof force === 'boolean' ? force : !sb.classList.contains('is-open');
      sb.classList.toggle('is-open', willOpen);
      const btn = utils.qs('.sidebar-toggle');
      if (btn) btn.setAttribute('aria-expanded', String(willOpen));
    }

    function closeSidebar() { toggleSidebar(false); }

    function bindClicks(root) {
      utils.on(root, 'click', (ev) => {
        const navItem = ev.target.closest('.nav-item[data-view]');
        if (!navItem) return;
        if (navItem.dataset.view === 'legacy-workbench' || navItem.classList.contains('nav-item--external')) {
          if (utils.isMobileViewport()) closeSidebar();
          return;
        }
        ev.preventDefault();
        switchTo(navItem.dataset.view);
      });

      utils.on(root, 'click', (ev) => {
        if (ev.target.closest('.sidebar-toggle')) {
          ev.preventDefault();
          toggleSidebar();
        }
      });

      utils.on(root, 'click', (ev) => {
        if (!utils.isMobileViewport()) return;
        const sb = utils.qs('.sidebar');
        if (!sb || !sb.classList.contains('is-open')) return;
        if (ev.target.closest('.sidebar')) return;
        if (ev.target.closest('.sidebar-toggle')) return;
        closeSidebar();
      });
    }

    function init() {
      const initial = (utils.qs('.nav-item.is-active[data-view]') || utils.qs('.nav-item[data-view="intel"]'));
      if (initial) setActive(initial.dataset.view);
      else setActive('intel');
      bindClicks(document);
      apiCache = { switchTo, setActive, closeSidebar, toggleSidebar, state };
    }

    return {
      init,
      switchTo,
      setActive,
      toggleSidebar,
      closeSidebar,
      state,
      get api() { return apiCache || {}; },
    };
  })();

  // ────────────────────────────────────────────────────────────────────────
  //  Number counter (rAF + easeOutCubic)
  // ────────────────────────────────────────────────────────────────────────
  const Counter = (() => {
    function format(el, current) {
      const decimals = (el && el.dataset && el.dataset.decimals) ? parseInt(el.dataset.decimals, 10) : 0;
      if (decimals > 0) return current.toFixed(decimals);
      return utils.formatThousands(current);
    }

    function animateOne(el) {
      if (el.dataset.counting === '1') return;
      const raw = el.dataset.target;
      const target = parseFloat(raw);
      if (!isFinite(target)) {
        el.textContent = raw;
        return;
      }

      if (ReducedMotion.enabled) {
        el.textContent = format(el, target);
        el.dataset.counting = '0';
        return;
      }

      el.dataset.counting = '1';
      const duration = CONFIG.COUNTER_DURATION_MS;
      const start = performance.now();
      function step(now) {
        const t = Math.min(1, (now - start) / duration);
        const eased = utils.easeOutCubic(t);
        const value = target * eased;
        el.textContent = format(el, value);
        if (t < 1) {
          requestAnimationFrame(step);
        } else {
          el.textContent = format(el, target);
          el.dataset.counting = '0';
        }
      }
      requestAnimationFrame(step);
    }

    function runInView(viewEl) {
      if (!viewEl) return;
      utils.qsa('.intel-number[data-target]', viewEl).forEach(animateOne);
    }

    function init() {
      utils.idleCallback(() => {
        const firstView = utils.qs('.view.is-visible') || utils.qs('.view[data-view]');
        runInView(firstView);
      });

      document.addEventListener('view:enter', (ev) => {
        const viewName = ev && ev.detail && ev.detail.view;
        const v = utils.qs('.view[data-view="' + viewName + '"]');
        runInView(v);
      });
    }

    return { init, animateOne, runInView };
  })();

  // ────────────────────────────────────────────────────────────────────────
  //  Pulse bar (status indicators + ticking label)
  // ────────────────────────────────────────────────────────────────────────
  const Pulse = (() => {
    let ticks = 0;
    let labelEl = null;
    let timer = null;

    function staggerDots() {
      utils.qsa('.pulse-dot[data-stream]').forEach((dot) => {
        const delay = (Math.floor(Math.random() * 1200)) + 'ms';
        dot.style.animationDelay = delay;
      });
    }

    function ensureLabel() {
      if (labelEl) return labelEl;
      labelEl = utils.qs('.pulse-status');
      if (!labelEl) {
        labelEl = document.createElement('span');
        labelEl.className = 'pulse-status';
        labelEl.setAttribute('aria-live', 'polite');
        const host = utils.qs('.pulse-bar');
        if (host) host.appendChild(labelEl);
      }
      return labelEl;
    }

    function updateLabel() {
      const el = ensureLabel();
      if (!el) return;
      ticks += 1;
      const seconds = Math.max(1, ticks);
      el.textContent = 'Last update ' + seconds + 's ago';
      el.dataset.seconds = String(seconds);
    }

    function start() {
      ensureLabel();
      staggerDots();
      updateLabel();
      if (timer) clearInterval(timer);
      timer = setInterval(updateLabel, CONFIG.PULSE_INTERVAL_MS);
    }

    function init() {
      utils.idleCallback(start);
    }

    return { init };
  })();

  // ────────────────────────────────────────────────────────────────────────
  //  Service health check (throttled, non-blocking, paused when hidden)
  // ────────────────────────────────────────────────────────────────────────
  const Health = (() => {
    let timer = null;
    let inFlight = false;
    let status = 'unknown';

    function setLoading() {
      status = 'loading';
      const dot = utils.qs('#status-dot');
      const text = utils.qs('#status-text');
      if (dot) dot.className = 'is-loading';
      if (text) text.textContent = '正在连接分析服务';
    }

    function setOk(payload) {
      status = 'ok';
      const dot = utils.qs('#status-dot');
      const text = utils.qs('#status-text');
      if (dot) dot.className = 'is-ok';
      if (text) text.textContent = '服务正常';

      if (payload && typeof payload === 'object') {
        const provider = utils.qs('#provider-name');
        const model = utils.qs('#model-name');
        const endpoint = utils.qs('#endpoint-text');
        if (provider && payload.provider) provider.textContent = String(payload.provider);
        if (model && payload.model) model.textContent = String(payload.model);
        if (endpoint && payload.endpoint) endpoint.textContent = String(payload.endpoint);
      }
    }

    function setError() {
      status = 'error';
      const dot = utils.qs('#status-dot');
      const text = utils.qs('#status-text');
      if (dot) dot.className = 'is-error';
      if (text) text.textContent = '连接中断';

      const slots = [utils.qs('#provider-name'), utils.qs('#model-name'), utils.qs('#endpoint-text')];
      slots.forEach((el) => {
        if (el && el.textContent.trim() === '') el.textContent = '-';
      });
    }

    async function fetchHealth() {
      if (inFlight) return;
      inFlight = true;
      try {
        const ctl = (typeof AbortController !== 'undefined') ? new AbortController() : null;
        const timeout = ctl ? setTimeout(() => ctl.abort(), 8000) : null;
        const res = await fetch(CONFIG.HEALTH_ENDPOINT, {
          method: 'GET',
          credentials: 'same-origin',
          headers: { Accept: 'application/json' },
          signal: ctl ? ctl.signal : undefined,
        });
        if (timeout) clearTimeout(timeout);
        if (!res.ok) { setError(); return; }
        let payload = null;
        try { payload = await res.json(); } catch (e) { payload = null; }
        setOk(payload);
      } catch (e) {
        setError();
      } finally {
        inFlight = false;
      }
    }

    function start() {
      setLoading();
      fetchHealth();
      if (timer) clearInterval(timer);
      timer = setInterval(fetchHealth, CONFIG.HEALTH_INTERVAL_MS);
    }

    function init() {
      document.addEventListener('visibilitychange', () => {
        if (document.hidden) {
          if (timer) { clearInterval(timer); timer = null; }
        } else if (!timer) {
          fetchHealth();
          timer = setInterval(fetchHealth, CONFIG.HEALTH_INTERVAL_MS);
        }
      });
      utils.idleCallback(start, { timeout: 1500 });
    }

    return { init, fetchHealth, get status() { return status; } };
  })();

  // ────────────────────────────────────────────────────────────────────────
  //  Project cards (delegated click → toast + log)
  // ────────────────────────────────────────────────────────────────────────
  const Projects = (() => {
    function bind(root) {
      utils.on(root, 'click', (ev) => {
        const card = ev.target.closest('.project-card[data-project-id]');
        if (!card) return;
        ev.preventDefault();
        const id = card.dataset.projectId || 'unknown';
        const titleEl = card.querySelector('.project-title, .project-name, h3, h4, .card-title');
        const title = titleEl ? titleEl.textContent.trim() : id;
        console.log('[Strategy Cockpit] Opening project:', id, title);
        Toast.show('正在打开项目 ' + title + '…', 'info');
      });
    }
    function init() { bind(document); }
    return { init };
  })();

  // ────────────────────────────────────────────────────────────────────────
  //  Skill cards (multi-select toggle + console + agent hint)
  // ────────────────────────────────────────────────────────────────────────
  const Skills = (() => {
    function selectedList(root) {
      return utils.qsa('.skill-card.is-active[data-skill]', root)
        .map((el) => el.dataset.skill);
    }

    function refreshAgentButton() {
      const btn = utils.qs('.btn-call-agent');
      if (!btn) return;
      const count = selectedList(document).length;
      btn.classList.toggle('is-ready', count > 0);
      btn.setAttribute('aria-disabled', count > 0 ? 'false' : 'true');
      const label = btn.querySelector('.agent-label');
      const text = count > 0
        ? '调用 Agent · ' + count + ' 项技能'
        : '调用 Agent';
      if (label) label.textContent = text;
      else btn.textContent = text;
    }

    function bind(root) {
      utils.on(root, 'click', (ev) => {
        const card = ev.target.closest('.skill-card[data-skill]');
        if (!card) return;
        ev.preventDefault();
        card.classList.toggle('is-active');
        card.setAttribute('aria-pressed', card.classList.contains('is-active') ? 'true' : 'false');
        const list = selectedList(document);
        console.log('[Strategy Cockpit] Selected skills:', list.slice());
        refreshAgentButton();
      });
    }

    function init() {
      bind(document);
      refreshAgentButton();
    }

    return { init, selectedList, refreshAgentButton };
  })();

  // ────────────────────────────────────────────────────────────────────────
  //  Plugin cards — visual toggle hook
  // ────────────────────────────────────────────────────────────────────────
  const Plugins = (() => {
    function bind(root) {
      utils.on(root, 'click', (ev) => {
        const card = ev.target.closest('.plugin-card[data-plugin]');
        if (!card) return;
        card.classList.toggle('is-active');
        console.log('[Strategy Cockpit] Plugin toggled:', card.dataset.plugin,
          card.classList.contains('is-active'));
      });
    }
    function init() { bind(document); }
    return { init };
  })();

  // ────────────────────────────────────────────────────────────────────────
  //  Agent cards / Call Agent button → legacy workbench (new tab)
  // ────────────────────────────────────────────────────────────────────────
  const Agents = (() => {
    function bind(root) {
      utils.on(root, 'click', (ev) => {
        const btn = ev.target.closest('.btn-call-agent');
        if (!btn) return;
        const card = btn.closest('.agent-card[data-agent]');
        const params = new URLSearchParams();
        if (card && card.dataset.agent) params.set('agent', card.dataset.agent);
        const skills = Skills.selectedList(document);
        if (skills.length) params.set('skills', skills.join(','));
        const url = CONFIG.LEGACY_WORKBENCH + (params.toString() ? ('?' + params.toString()) : '');
        if (ev.ctrlKey || ev.metaKey || ev.shiftKey) return; // user override → browser default
        ev.preventDefault();
        window.open(url, '_blank', 'noopener,noreferrer');
        console.log('[Strategy Cockpit] Calling agent →', url);
      });
    }
    function init() { bind(document); }
    return { init };
  })();

  // ────────────────────────────────────────────────────────────────────────
  //  Intelligence download button (per intel-card)
  // ────────────────────────────────────────────────────────────────────────
  const Downloads = (() => {
    function bind(root) {
      utils.on(root, 'click', (ev) => {
        const btn = ev.target.closest('.btn-download');
        if (!btn) return;
        ev.preventDefault();
        const card = btn.closest('.intel-card[data-domain]');
        const domain = card ? card.dataset.domain : 'intel';
        console.log('[Strategy Cockpit] Downloading intel:', domain);
        Toast.show('已生成情报快照：' + domain, 'success');
        try {
          const blob = new Blob([
            JSON.stringify({
              domain, generatedAt: new Date().toISOString(),
              note: 'Strategy Cockpit mock intelligence export.',
            }, null, 2),
          ], { type: 'application/json' });
          const url = URL.createObjectURL(blob);
          const a = document.createElement('a');
          a.href = url;
          a.download = 'cockpit-' + domain + '-' + Date.now() + '.json';
          document.body.appendChild(a);
          a.click();
          setTimeout(() => { URL.revokeObjectURL(url); a.remove(); }, 0);
        } catch (e) { /* non-fatal */ }
      });
    }
    function init() { bind(document); }
    return { init };
  })();

  // ────────────────────────────────────────────────────────────────────────
  //  Keyboard shortcuts
  //  • 1..7  → switch main nav (ignores text-entry focus)
  //  • Esc   → close sidebar drawer (mobile)
  //  • Ctrl/Cmd + K → reserved (no-op for now)
  // ────────────────────────────────────────────────────────────────────────
  const Shortcuts = (() => {
    function isTextEntry(el) {
      if (!el) return false;
      const tag = (el.tagName || '').toLowerCase();
      if (tag === 'input' || tag === 'textarea' || tag === 'select') return true;
      if (el.isContentEditable) return true;
      return false;
    }

    function handle(ev) {
      if ((ev.ctrlKey || ev.metaKey) && (ev.key === 'k' || ev.key === 'K')) {
        return; // reserved for future search focus
      }

      if (ev.key === 'Escape') {
        const sb = utils.qs('.sidebar');
        if (sb && sb.classList.contains('is-open')) {
          ev.preventDefault();
          Navigation.closeSidebar();
        }
        return;
      }

      if (isTextEntry(ev.target)) return;
      const map = { '1': 0, '2': 1, '3': 2, '4': 3, '5': 4, '6': 5, '7': 6 };
      if (!Object.prototype.hasOwnProperty.call(map, ev.key)) return;
      const navItems = utils.qsa('.sidebar .nav-section:not([data-section="history"]) .nav-item[data-view]')
        .filter((n) => CONFIG.MAIN_NAV_KEYS.includes(n.dataset.view));
      const idx = map[ev.key];
      if (idx < navItems.length) {
        ev.preventDefault();
        Navigation.switchTo(navItems[idx].dataset.view);
      }
    }

    function init() {
      utils.on(document, 'keydown', handle);
    }

    return { init };
  })();

  // ────────────────────────────────────────────────────────────────────────
  //  View transition polish (lightweight class fade; CSS-driven)
  // ────────────────────────────────────────────────────────────────────────
  const Transition = (() => {
    function init() {
      const ws = utils.qs('.workspace');
      if (!ws) return;
      document.addEventListener('view:enter', () => {
        if (ReducedMotion.enabled) return;
        ws.classList.remove('is-fading');
        // Force reflow then re-add to retrigger the CSS transition.
        void ws.offsetWidth;
        ws.classList.add('is-fading');
        setTimeout(() => ws.classList.remove('is-fading'), CONFIG.VIEW_TRANSITION_MS + 30);
      });
    }
    return { init };
  })();

  // ────────────────────────────────────────────────────────────────────────
  //  Bootstrap
  // ────────────────────────────────────────────────────────────────────────
  function init() {
    ReducedMotion.init();
    Navigation.init();
    Transition.init();
    Counter.init();
    Projects.init();
    Skills.init();
    Plugins.init();
    Agents.init();
    Downloads.init();
    Shortcuts.init();
    Pulse.init();
    Health.init();
    KouBei.init();

    window.Home = Object.freeze({
      version: '1.0.0',
      switchView: Navigation.switchTo,
      showToast: Toast.show,
      getSelectedSkills: () => Skills.selectedList(document),
      getStatus: () => Health.status,
      get reducedMotion() { return ReducedMotion.enabled; },
    });
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init, { once: true });
  } else {
    init();
  }
})();
