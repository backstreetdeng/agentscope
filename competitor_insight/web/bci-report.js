/* ==========================================================================
   竞品洞察 ④ 报告输出
   - 一个目标车型一份报告；版本线 v1.0 → v1.1 → v1.2；
   - 只接真实接口 /api/bci/report/*，不做假入口；
   - 改稿只提交受控指令：设标题 / 截断要点 / 追加来源引用。
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
    compare: null,
    busy: false,
    status: null,
    revise: { op: "set_title", target: "", value: "", count: 3, refs: "" },
  };

  function esc(value) {
    return String(value === null || value === undefined ? "" : value).replace(/[&<>"']/g, function (ch) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[ch];
    });
  }

  function num(value) {
    return typeof value === "number" ? value : 0;
  }

  function when(value) {
    return String(value || "").replace("T", " ").slice(0, 16);
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

  function model() {
    const models = (state.options && state.options.models) || [];
    return (
      models.find(function (item) {
        return item.key === state.selected;
      }) || null
    );
  }

  function modelsHtml() {
    const models = (state.options && state.options.models) || [];
    if (!models.length) return "<p class='bci-r-hint'>车型清单为空，请检查 analysis_models.json。</p>";
    return (
      "<div class='bci-r-models'>" +
      models
        .map(function (item) {
          const archive = item.archive || {};
          return (
            "<label class='bci-r-model'>" +
            "<input type='radio' name='bci-r-model' data-model='" +
            esc(item.key) +
            "'" +
            (state.selected === item.key ? " checked" : "") +
            ">" +
            "<b>" +
            esc(item.label) +
            "</b><span>定量 " +
            esc(num((item.sources || {}).quant)) +
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
    const item = model();
    const archive = (state.options && state.options.archive) || {};
    return (
      "<div class='bci-r-card'>" +
      "<h4>生成配置<small>" +
      esc((state.options && state.options.outline && state.options.outline.version) || "") +
      "</small></h4>" +
      "<p class='bci-r-hint'>一个目标车型一份报告，只覆盖竞品侧；定性部分按档案人数展示，不出比例。</p>" +
      "<h4 style='font-size:12.5px;margin-top:4px'>目标车型</h4>" +
      modelsHtml() +
      "<div class='bci-r-scope'>" +
      "<div><span>定量样本</span><b>" +
      esc(item ? num((item.sources || {}).quant) : 0) +
      "</b></div>" +
      "<div><span>深访访谈</span><b>" +
      esc(item ? num((item.archive || {}).interview_total) : 0) +
      "</b></div>" +
      "<div><span>已生成档案</span><b>" +
      esc(item ? num((item.archive || {}).archived) : 0) +
      "</b></div>" +
      "<div><span>档案模板</span><b>" +
      esc(archive.template_version || "—") +
      "</b></div>" +
      "</div>" +
      "<h4 style='font-size:12.5px'>本期页面</h4>" +
      pagesHtml() +
      "<div class='bci-r-actions'>" +
      "<button type='button' class='bci-r-btn bci-r-btn--primary' data-action='generate'" +
      (state.busy || !state.selected ? " disabled" : "") +
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
      return "<p class='bci-r-hint'>该车型还没有报告版本。点击「生成报告」创建 v1.0。</p>";
    }
    return (
      "<div class='bci-r-versions'>" +
      state.versions
        .map(function (item) {
          const active = state.current === item.report_version_id;
          const stale = item.status === "stale";
          const revised = item.revision_kind === "revise";
          return (
            "<button type='button' class='bci-r-version" +
            (active ? " is-active" : "") +
            "' data-version='" +
            esc(item.report_version_id) +
            "'>" +
            "<b>" +
            esc(item.version_label) +
            "</b>" +
            (revised ? "<span class='bci-r-tag'>改稿</span>" : "") +
            "<span>" +
            esc(when(item.generated_at)) +
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
      return "<div class='bci-r-empty'>选择目标车型生成报告，或从上方版本线打开历史版本。<br>生成的报告为静态 HTML，可下载留档。</div>";
    }
    const detail = state.detail;
    const meta = detail
      ? esc(detail.version_label) +
        " · " +
        esc(when(detail.generated_at)) +
        " · " +
        (detail.revision_kind === "revise" ? "改稿" : "生成") +
        " · 指纹 " +
        esc(String((detail.content && detail.content.data_fingerprint) || "").slice(0, 12))
      : "版本 " + esc((state.current || "").slice(0, 8));
    const banner = detail && detail.stale
      ? "<div class='bci-r-banner'>该版本已过期：" + esc(detail.stale_reason || "底层数据已变化") + "。请重新生成。</div>"
      : "";
    const compareBtn = detail && detail.parent_version_id
      ? "<button type='button' class='bci-r-btn' data-action='compare'>与上一版对比</button>"
      : "";
    return (
      "<div class='bci-r-view'>" +
      "<div class='bci-r-view__head'>" +
      "<div class='bci-r-view__meta'><b>报告预览</b><br>" +
      meta +
      "</div>" +
      "<div class='bci-r-view__actions'>" +
      compareBtn +
      "<button type='button' class='bci-r-btn' data-action='download'>下载 HTML</button>" +
      "<button type='button' class='bci-r-btn' data-action='regenerate'" +
      (state.busy ? " disabled" : "") +
      ">重新生成</button>" +
      "</div></div>" +
      banner +
      "<iframe class='bci-r-frame' referrerpolicy='no-referrer' src='/api/bci/report/preview?id=" +
      encodeURIComponent(state.current) +
      "' title='报告预览'></iframe>" +
      "</div>"
    );
  }

  function blockOptions() {
    const content = state.detail && state.detail.content;
    if (!content) return [];
    const pages = (content.pages || []).concat(content.appendices || []);
    const out = [];
    pages.forEach(function (page) {
      out.push({ value: "page:" + page.page, label: "页 " + page.page + " · " + page.title });
      (page.blocks || []).forEach(function (block) {
        if (state.revise.op === "limit_items" && block.type !== "bullets") return;
        out.push({ value: "block:" + block.id, label: "块 " + block.id + " · " + block.title });
      });
    });
    return out;
  }

  function reviseHtml() {
    if (!state.detail) {
      return "<div class='bci-r-card'><h4>报告校核</h4><p class='bci-r-hint'>先打开一个版本，再下达受控改稿指令。</p></div>";
    }
    const options = blockOptions();
    const op = state.revise.op;
    const valueField =
      op === "set_title"
        ? "<label class='bci-r-field'><span>新标题（1–60 字）</span><input data-revise='value' maxlength='60' value='" +
          esc(state.revise.value) +
          "' placeholder='例：竞品流失去向'></label>"
        : op === "limit_items"
          ? "<label class='bci-r-field'><span>保留条数（1–20）</span><input type='number' min='1' max='20' data-revise='count' value='" +
            esc(state.revise.count) +
            "'></label>"
          : "<label class='bci-r-field'><span>引用块（逗号分隔）</span><input data-revise='refs' value='" +
            esc(state.revise.refs) +
            "' placeholder='例：P04.TOP5, P11.BULLETS'></label>";
    return (
      "<div class='bci-r-card'>" +
      "<h4>报告校核<small>只落新版本，不覆盖旧版</small></h4>" +
      "<p class='bci-r-hint'>只开放三种确定性指令：设标题、要点截断、追加来源引用。不允许自由改写正文与数字。</p>" +
      "<div class='bci-r-revise'>" +
      "<label class='bci-r-field'><span>指令</span><select data-revise='op'>" +
      "<option value='set_title'" + (op === "set_title" ? " selected" : "") + ">设标题</option>" +
      "<option value='limit_items'" + (op === "limit_items" ? " selected" : "") + ">要点截断</option>" +
      "<option value='append_refs'" + (op === "append_refs" ? " selected" : "") + ">追加来源引用</option>" +
      "</select></label>" +
      "<label class='bci-r-field'><span>目标</span><select data-revise='target'>" +
      options
        .map(function (item) {
          return "<option value='" + esc(item.value) + "'" + (state.revise.target === item.value ? " selected" : "") + ">" + esc(item.label) + "</option>";
        })
        .join("") +
      "</select></label>" +
      valueField +
      "<button type='button' class='bci-r-btn bci-r-btn--primary' data-action='revise'" +
      (state.busy ? " disabled" : "") +
      ">生成新版本</button>" +
      "</div>" +
      "</div>"
    );
  }

  function compareHtml() {
    if (!state.compare) {
      return "<div class='bci-r-card'><h4>版本对比</h4><p class='bci-r-hint'>打开一个改稿版本后点击「与上一版对比」，按内容块与行键并排显示变化。</p></div>";
    }
    const diff = state.compare;
    const pages = diff.pages.filter(function (page) {
      return page.changed;
    });
    return (
      "<div class='bci-r-card'>" +
      "<h4>版本对比<small>" +
      esc(diff.base.version_label) +
      " → " +
      esc(diff.target.version_label) +
      " · 变化块 " +
      esc(diff.changed_blocks) +
      "</small></h4>" +
      (pages.length
        ? pages
            .map(function (page) {
              const blocks = page.blocks.filter(function (block) {
                return block.changed;
              });
              return (
                "<div class='bci-r-diff'>" +
                "<div class='bci-r-diff__page'>" +
                esc(page.page) +
                " · " +
                esc(page.title) +
                "</div>" +
                blocks
                  .map(function (block) {
                    return (
                      "<div class='bci-r-diff__block'><b>" +
                      esc(block.id) +
                      "</b> " +
                      esc(block.title || "") +
                      (block.row_changes.length
                        ? "<table class='bci-r-diff__table'><tbody>" +
                          block.row_changes
                            .map(function (row) {
                              return (
                                "<tr data-change='" +
                                esc(row.change) +
                                "'><td>" +
                                esc(row.key) +
                                "</td><td>" +
                                esc(row.before === null ? "—" : row.before) +
                                "</td><td>" +
                                esc(row.after === null ? "—" : row.after) +
                                "</td></tr>"
                              );
                            })
                            .join("") +
                          "</tbody></table>"
                        : "<span class='bci-r-diff__meta'>标题 / 引用变化</span>") +
                      "</div>"
                    );
                  })
                  .join("") +
                "</div>"
              );
            })
            .join("")
        : "<p class='bci-r-hint'>两个版本没有内容变化。</p>") +
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
      "<p>一个目标车型一份报告：按固定大纲生成定量、流失、满意度与深访原话，生成后固化为版本；校核只做受控改稿并落成 v1.1、v1.2。</p>" +
      "</div>" +
      "<div class='bci-r-top__actions'><span class='bci-r-hint' style='margin:0'>同步生成，约 20–30 秒</span></div>" +
      "</div>" +
      "<div class='bci-r-grid'>" +
      configHtml() +
      "<div class='bci-r-card'><h4>版本线<small>" +
      esc(state.versions.length) +
      " 个版本</small></h4>" +
      versionsHtml() +
      "<div style='height:12px'></div>" +
      viewHtml() +
      "</div>" +
      "</div>" +
      "<div class='bci-r-grid'>" +
      reviseHtml() +
      compareHtml() +
      "</div>";
  }

  async function loadOptions() {
    state.options = await api("/api/bci/report/options");
    if (!state.selected) {
      const models = state.options.models || [];
      const preferred = models.find(function (item) {
        return item.key === state.options.default_model;
      });
      state.selected = (preferred || models[0] || {}).key || null;
    }
  }

  async function loadVersions() {
    if (!state.selected) {
      state.versions = [];
      return;
    }
    const data = await api("/api/bci/report/versions?limit=50&model_key=" + encodeURIComponent(state.selected));
    state.versions = data.items || [];
  }

  async function openVersion(id) {
    state.current = id;
    state.detail = null;
    state.compare = null;
    state.revise.target = "";
    render();
    try {
      state.detail = await api("/api/bci/report/detail?id=" + encodeURIComponent(id));
      if (!state.revise.target) {
        const options = blockOptions();
        state.revise.target = options.length ? options[0].value : "";
      }
      render();
    } catch (err) {
      state.status = { kind: "error", text: err.message };
      render();
    }
  }

  async function generate() {
    if (state.busy || !state.selected) return;
    state.busy = true;
    state.status = { kind: "", text: "生成中：正在取数与渲染，预计 20–30 秒。" };
    render();
    const started = Date.now();
    try {
      const data = await api("/api/bci/report/generate", {
        method: "POST",
        body: JSON.stringify({ model_key: state.selected }),
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
          "：" +
          data.version_label +
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

  async function submitRevision() {
    if (state.busy || !state.current) return;
    const target = state.revise.target || "";
    if (!target) {
      setStatus("error", "请选择改稿目标。");
      return;
    }
    const targetSpec = target.indexOf("page:") === 0 ? { page: target.slice(5) } : { block: target.slice(6) };
    const operation = { op: state.revise.op, target: targetSpec };
    if (state.revise.op === "set_title") operation.value = state.revise.value.trim();
    if (state.revise.op === "limit_items") operation.count = Number(state.revise.count);
    if (state.revise.op === "append_refs") {
      operation.refs = state.revise.refs
        .split(/[,，\s]+/)
        .map(function (item) {
          return item.trim();
        })
        .filter(Boolean);
    }
    state.busy = true;
    state.status = { kind: "", text: "正在按受控指令生成新版本…" };
    render();
    try {
      const data = await api("/api/bci/report/revise", {
        method: "POST",
        body: JSON.stringify({ report_version_id: state.current, operations: [operation] }),
      });
      await loadVersions();
      state.busy = false;
      await openVersion(data.report_version_id);
      state.status = { kind: "ok", text: "已生成 " + data.version_label + "，父版本保持不变。" };
      render();
    } catch (err) {
      state.busy = false;
      state.status = { kind: "error", text: err.message };
      render();
    }
  }

  async function runCompare() {
    if (!state.detail || !state.detail.parent_version_id) return;
    try {
      state.compare = await api(
        "/api/bci/report/compare?base=" +
          encodeURIComponent(state.detail.parent_version_id) +
          "&target=" +
          encodeURIComponent(state.current)
      );
      render();
    } catch (err) {
      setStatus("error", err.message);
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
      const radio = ev.target.closest("input[data-model]");
      if (radio) {
        state.selected = radio.getAttribute("data-model");
        state.current = null;
        state.detail = null;
        state.compare = null;
        state.status = null;
        loadVersions()
          .then(function () {
            return state.versions.length ? openVersion(state.versions[0].report_version_id) : render();
          })
          .catch(function (err) {
            setStatus("error", err.message);
          });
        return;
      }
      const field = ev.target.closest("[data-revise]");
      if (field) {
        const name = field.getAttribute("data-revise");
        state.revise[name] = field.value;
        if (name === "op") {
          state.revise.target = "";
          const options = blockOptions();
          state.revise.target = options.length ? options[0].value : "";
        }
        render();
      }
    });
    state.host.addEventListener("click", function (ev) {
      const action = ev.target.closest("[data-action]");
      if (action) {
        const name = action.getAttribute("data-action");
        if (name === "generate" || name === "regenerate") generate();
        if (name === "download") download();
        if (name === "revise") submitRevision();
        if (name === "compare") runCompare();
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
