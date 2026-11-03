/* 竞品对标工作区（MKT-001）：片段注入 + 交互绑定，与 forecast-engine 同款加载方式 */
(function () {
  'use strict';

  var MOUNT_ID = 'benchmark-mount';
  var loaded = false;
  var loading = false;
  var running = false;

  function $(id) { return document.getElementById(id); }

  function setStatus(message, kind) {
    var el = $('bm-status');
    if (!el) return;
    el.textContent = message;
    el.className = 'bm-status' + (kind ? ' is-' + kind : '');
  }

  function renderTools(events) {
    var box = $('bm-tools');
    if (!box) return;
    if (!events.length) {
      box.innerHTML = '<div class="bm-tool"><span class="bm-tool__detail">无工具调用记录</span></div>';
    } else {
      box.innerHTML = events.map(function (ev) {
        var status = String(ev.status || '');
        var cls = status === 'success' ? 'is-success' : status === 'error' ? 'is-error' : 'is-warning';
        return '<div class="bm-tool">' +
          '<span class="bm-tool__status ' + cls + '">' + escapeHtml(status) + '</span>' +
          '<span class="bm-tool__name">' + escapeHtml(ev.name || '') + '</span>' +
          '<span class="bm-tool__detail">' + escapeHtml(String(ev.detail || '').slice(0, 220)) + '</span>' +
          '</div>';
      }).join('');
    }
    $('bm-tools-panel').hidden = false;
  }

  function escapeHtml(value) {
    return String(value).replace(/[&<>"']/g, function (ch) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[ch];
    });
  }

  async function run(event) {
    if (event) event.preventDefault();
    if (running) return;
    var target = $('bm-target');
    var query = target ? target.value.trim() : '';
    if (!query) { setStatus('请输入目标车型。', 'error'); return; }

    running = true;
    var button = $('bm-run');
    if (button) button.disabled = true;
    setStatus('正在取证…（款型配置信息 → 口碑 → 联网，可能需要数十秒）', 'running');
    $('bm-answer-panel').hidden = true;
    $('bm-tools-panel').hidden = true;

    try {
      var response = await fetch('/api/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          question: query,
          agent: 'competitor_benchmark',
          analysis_type: 'competitor_benchmark',
          capabilities: [],
          mcp_plugins: ['reputation']
        })
      });
      var data = await response.json();
      if (!response.ok) throw new Error(data && data.error ? data.error : ('请求失败 HTTP ' + response.status));
      $('bm-answer').textContent = data.answer || '(无正文)';
      $('bm-answer-panel').hidden = false;
      renderTools(Array.isArray(data.tool_events) ? data.tool_events : []);
      setStatus('完成。');
    } catch (error) {
      setStatus('出错：' + (error && error.message ? error.message : error), 'error');
    } finally {
      running = false;
      if (button) button.disabled = false;
    }
  }

  async function load() {
    if (loaded || loading) return;
    loading = true;
    var root = $(MOUNT_ID);
    if (!root) { loading = false; return; }
    try {
      var response = await fetch('/benchmark-view');
      if (!response.ok) throw new Error('竞品对标工作区加载失败。');
      root.innerHTML = await response.text();
      var form = $('bm-form');
      if (form) form.addEventListener('submit', run);
      loaded = true;
    } catch (error) {
      root.textContent = (error && error.message ? error.message : String(error)) + ' 请刷新页面重试。';
    } finally {
      loading = false;
    }
  }

  document.addEventListener('view:enter', function (event) {
    if (event.detail && event.detail.view === 'benchmark') load();
  });
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', function () { if (location.hash === '#benchmark') load(); });
  } else if (location.hash === '#benchmark') {
    load();
  }
}());
