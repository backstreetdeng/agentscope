/* ==========================================================================
   竞品洞察 ④ 报告输出
   - 只接真实接口 /api/bci/report/*，不做假入口；
   - 生成是同步请求，期间按钮置灰并提示预计耗时；
   - 版本列表与预览都来自服务端，过期版本只提示不隐藏。
   ========================================================================== */
(function () {
  "use strict";

  const state = {
    host: null,
    options: null,
    selected: null,
    versions: [],
    current: null,
    detail: null,
    busy: false,
    status: null,
  };

  function esc(value) {
    return String(value === null || value === undefined ? "" : value).replace(/[&<>"']/g, function (ch) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[ch];
    });
  }

  function num(value) {
    return typeof value === "number" ? value : 0;
  }

  async function api(path, init) {
    const request = Object.assign({ headers: { "Content-Type": "application/json" } }, init || {});
    const res = await fetch(path, request);
    let body = null;
    try {
      body = await res.json();
    } catch (err) {
      body = null;
    }
    if (!res.ok || !body || body.ok !== true) {
      const error = (body && body.error) || {};
      throw new Error(error.message || "请求失败（HTTP " + res.status + "）");
    }
    return body.data;
  }

  function setStatus(kind, text) {
    state.status = text ? { kind: kind, text: text } : null;
    render();
  }

  function totals() {
    const options = state.options || { models: [] };
    const chosen = (options.models || []).filter(function (model) {
      return state.selected.has(model.key);
    });
    const sum = function (fn) {
      return chosen.reduce(function (acc, model) {
        return acc + fn(model);
      }, 0);
    };
    return {
      models: chosen,
      quant: sum(function (model) {
        return num((model.sources || {}).quant);
      }),
      interviews: sum(function (model) {
        return num((model.archive || {}).interview_total);
      }),
      archived: sum(function (model) {
        return num((model.archive || {}).archived);
      }),
    };
  }

  function modelsHtml() {
    const models = (state.options && state.options.models) || [];
    if (!models.length) return "<p class='bci-r-hint'>车型清单为空，请检查 analysis_models.json。</p>";
    return (
      "<div class='bci-r-models'>" +
      models
        .map(function (model) {
          const archive = model.archive || {};
          return (
            "<label class='bci-r-model'>" +
            "<input type='checkbox' data-model='" +
            esc(model.key) +
            "'" +
            (state.selected.has(model.key) ? " checked" : "") +
            ">" +
            "<b>" +
            esc(model.label) +
            "</b>" +
            "<span>定量 " +
            esc(num((model.sources || {}).quant)) +
            " · 档案 " +
            esc(num(archive.archived)) +
            "/" +
            esc(num(archive.interview_total)) +
            "</span></label>"
          );
        })
        .join("") +
      "</div>"
    );
  }

  function pagesHtml() {
    const pages = (state.options && state.options.outline && state.options.outline.pages) || [];
    if (!pages.length) return "";
    return (
      "<ul class='bci-r-pages'>" +
      pages
        .map(function (page) {
          return "<li><b>" + esc(page.page) + "</b><span>" + esc(page.title) + "</span></li>";
        })
        .join("") +
      "</ul>"
    );
  }

  function configHtml() {
    const total = totals();
    const archive = (state.options && state.options.archive) || {};
    return (
      "<div class='bci-r-card'>" +
      "<h4>生成配置<small>" +
      esc((state.options && state.options.outline && state.options.outline.version) || "") +
      "</small></h4>" +
      "<p class='bci-r-hint'>报告为组竞品口径，只覆盖竞品侧；定性部分按档案人数展示，不出比例。</p>" +
      "<h4 style='font-size:12.5px;margin-top:4px'>车型范围</h4>" +
      modelsHtml() +
      "<div class='bci-r-scope'>" +
      "<div><span>定量样本</span><b>" +
      esc(total.quant) +
      "</b></div>" +
      "<div><span>深访访谈</span><b>" +
      esc(total.interviews) +
      "</b></div>" +
      "<div><span>已生成档案</span><b>" +
      esc(total.archived) +
      "</b></div>" +
      "<div><span>档案模板</span><b>" +
      esc(archive.template_version || "—") +
      "</b></div>" +
      "</div>" +
      "<h4 style='font-size:12.5px'>本期页面</h4>" +
      pagesHtml() +
      "<div class='bci-r-actions'>" +
      "<button type='button' class='bci-r-btn bci-r-btn--primary' data-action='generate'" +
      (state.busy || !state.selected.size ? " disabled" : "") +
      ">" +
      (state.busy ? "生成中…" : "生成报告") +
      "</button>" +
      "</div>" +
      (state.status
        ? "<p class='bci-r-status' data-state='" + esc(state.status.kind) + "'>" + esc(state.status.text) + "</p>"
        : "") +
      "</div>"
    );
  }

  function versionsHtml() {
    if (!state.versions.length) {
      return "<p class='bci-r-hint'>还没有报告版本。选择车型后点击「生成报告」。</p>";
    }
    return (
      "<div class='bci-r-versions'>" +
      state.versions
        .map(function (item) {
          const active = state.current === item.report_version_id;
          const stale = item.status === "stale";
          return (
            "<button type='button' class='bci-r-version" +
            (active ? " is-active" : "") +
            "' data-version='" +
            esc(item.report_version_id) +
            "'>" +
            "<b>v" +
            esc(item.version_no) +
            "</b><span>" +
            esc(String(item.generated_at || "").replace("T", " ").slice(0, 16)) +
            "</span>" +
            "<span class='" +
            (stale ? "is-stale" : "is-ok") +
            "'>" +
            (stale ? "已过期" : "有效") +
            "</span></button>"
          );
        })
        .join("") +
      "</div>"
    );
  }

  function viewHtml() {
    if (!state.current) {
      return "<div class='bci-r-empty'>选择左侧配置生成报告，或从上方版本列表打开历史版本。<br>生成的报告为静态 HTML，可下载留档。</div>";
    }
    const detail = state.detail;
    const meta = detail
      ? "v" +
        esc(detail.version_no) +
        " · " +
        esc(String(detail.generated_at || "").replace("T", " ").slice(0, 16)) +
        " · 指纹 " +
        esc(String((detail.content && detail.content.data_fingerprint) || "").slice(0, 12))
      : "v" + esc((state.current || "").slice(0, 8));
    const banner = detail && detail.stale
      ? "<div class='bci-r-banner'>该版本已过期：" + esc(detail.stale_reason || "底层数据已变化") + "。请重新生成。</div>"
      : "";
    return (
      "<div class='bci-r-view'>" +
      "<div class='bci-r-view__head'>" +
      "<div class='bci-r-view__meta'><b>报告预览</b><br>" +
      meta +
      "</div>" +
      "<div class='bci-r-view__actions'>" +
      "<button type='button' class='bci-r-btn' data-action='download'>下载 HTML</button>" +
      "<button type='button' class='bci-r-btn' data-action='regenerate'" +
      (state.busy ? " disabled" : "") +
      ">重新生成</button>" +
      "</div></div>" +
      banner +
      "<iframe class='bci-r-frame' sandbox='' referrerpolicy='no-referrer' src='/api/bci/report/preview?id=" +
      encodeURIComponent(state.current) +
      "' title='报告预览'></iframe>" +
      "</div>"
    );
  }

  function render() {
    if (!state.host) return;
    state.host.innerHTML =
      "<div class='bci-r-top'>" +
      "<div class='bci-r-top__text'>" +
      "<span class='bci-r-eyebrow'>Report Output</span>" +
      "<h3>报告输出</h3>" +
      "<p>按固定大纲生成组竞品洞察报告：定量分布、选择与流失、满意度、深访原话与外部口碑。生成后固化为版本，底层样本或档案变化会把旧版本标记为过期。</p>" +
      "</div>" +
      "<div class='bci-r-top__actions'><span class='bci-r-hint' style='margin:0'>同步生成，约 20–30 秒</span></div>" +
      "</div>" +
      "<div class='bci-r-grid'>" +
      configHtml() +
      "<div class='bci-r-card'><h4>版本与预览<small>" +
      esc(state.versions.length) +
      " 个版本</small></h4>" +
      versionsHtml() +
      "<div style='height:12px'></div>" +
      viewHtml() +
      "</div>" +
      "</div>";
  }

  async function loadOptions() {
    state.options = await api("/api/bci/report/options");
    if (!state.selected) {
      state.selected = new Set(
        (state.options.models || []).map(function (model) {
          return model.key;
        })
      );
    }
  }

  async function loadVersions() {
    const data = await api("/api/bci/report/versions?limit=20");
    state.versions = data.items || [];
  }

  async function openVersion(id) {
    state.current = id;
    state.detail = null;
    render();
    try {
      state.detail = await api("/api/bci/report/detail?id=" + encodeURIComponent(id));
      render();
    } catch (err) {
      state.status = { kind: "error", text: err.message };
      render();
    }
  }

  async function generate() {
    if (state.busy) return;
    const keys = Array.from(state.selected);
    if (!keys.length) {
      setStatus("error", "至少选择一款车型。");
      return;
    }
    state.busy = true;
    state.status = { kind: "", text: "生成中：已选 " + keys.length + " 款车型，正在取数与渲染，预计 20–30 秒。" };
    render();
    const started = Date.now();
    try {
      const data = await api("/api/bci/report/generate", {
        method: "POST",
        body: JSON.stringify({ model_keys: keys }),
      });
      await loadVersions();
      state.busy = false;
      state.current = data.report_version_id;
      state.detail = null;
      render();
      await openVersion(data.report_version_id);
      state.status = {
        kind: "ok",
        text:
          (data.reused ? "同版本数据已存在，复用已有报告" : "生成完成") +
          "：v" +
          data.version_no +
          "，耗时 " +
          ((Date.now() - started) / 1000).toFixed(1) +
          " 秒。",
      };
      render();
    } catch (err) {
      state.busy = false;
      state.status = { kind: "error", text: err.message };
      render();
    }
  }

  function download() {
    if (!state.current) return;
    window.location.href = "/api/bci/report/export?id=" + encodeURIComponent(state.current);
  }

  function bind() {
    if (state.host.dataset.bound === "1") return;
    state.host.dataset.bound = "1";
    state.host.addEventListener("change", function (ev) {
      const input = ev.target.closest("input[data-model]");
      if (!input) return;
      if (input.checked) state.selected.add(input.getAttribute("data-model"));
      else state.selected.delete(input.getAttribute("data-model"));
      render();
    });
    state.host.addEventListener("click", function (ev) {
      const action = ev.target.closest("[data-action]");
      if (action) {
        const name = action.getAttribute("data-action");
        if (name === "generate" || name === "regenerate") generate();
        if (name === "download") download();
        return;
      }
      const version = ev.target.closest("[data-version]");
      if (version) openVersion(version.getAttribute("data-version"));
    });
  }

  async function init(host) {
    if (!host || host.dataset.ready === "1") return;
    host.dataset.ready = "1";
    state.host = host;
    host.innerHTML = "<div class='bci-r-empty'>正在加载报告配置…</div>";
    try {
      await loadOptions();
      await loadVersions();
      bind();
      if (state.versions.length) {
        await openVersion(state.versions[0].report_version_id);
      } else {
        render();
      }
    } catch (err) {
      host.innerHTML =
        "<div class='bci-r-empty'>报告模块加载失败：" + esc(err.message) + "<br>请检查 7860 服务与数据库连接。</div>";
    }
  }

  window.BciReport = { init: init };
})();
