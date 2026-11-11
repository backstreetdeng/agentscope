/* ==========================================================================
   竞品洞察 ④ 报告输出
   - 一个目标车型一份报告；版本线 v1.0 → v1.1 → v1.2；
   - 左侧「标准化报告大纲」按 11 页导航，右侧只渲染当前页，导出仍是整篇；
   - 校核助手接受自然语言指令重写单页文案，数字与引语必须指回本页数据。
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
    page: "",
    revise: { page: "", instruction: "" },
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

  // ------------------------------------------------------------ 页面与大纲

  function pages() {
    const content = state.detail && state.detail.content;
    if (content && (content.pages || []).length) {
      return content.pages.map(function (page, index) {
        return { page: String(page.page), title: page.title || "", index: index + 1 };
      });
    }
    const outline = (state.options && state.options.outline && state.options.outline.pages) || [];
    return outline
      .filter(function (page) {
        return /^P\d{2}$/.test(String(page.page));
      })
      .map(function (page, index) {
        return { page: String(page.page), title: page.title || "", index: index + 1 };
      });
  }

  function pageIndex(pageId) {
    return pages().findIndex(function (item) {
      return item.page === pageId;
    });
  }

  function pickPage(candidate) {
    const list = pages();
    if (!list.length) return "";
    if (candidate && list.some(function (item) { return item.page === candidate; })) return candidate;
    return list[0].page;
  }

  function ensurePage() {
    state.page = pickPage(state.page);
    return state.page;
  }

  function pageLabel(pageId) {
    return String(pageId || "").replace(/^P0?/, "");
  }

  function pageTitleText(pageId) {
    const found = pages().find(function (item) {
      return item.page === pageId;
    });
    return found ? String(found.title || "").replace(/^\d+-/, "") : "";
  }

  function pageCounter(pageId) {
    const index = pageIndex(pageId);
    return pageId + " · 第 " + (index + 1) + " / " + pages().length + " 页";
  }

  function pageSrc(pageId) {
    return (
      "/api/bci/report/page?id=" +
      encodeURIComponent(state.current || "") +
      "&page=" +
      encodeURIComponent(pageId || "")
    );
  }

  function readDeepLink() {
    const query = new URLSearchParams(location.search);
    const version = query.get("report") || "";
    if (!/^[0-9a-fA-F-]{36}$/.test(version)) return null;
    const page = String(query.get("page") || "").toUpperCase();
    return { version: version, page: /^P\d{2}$/.test(page) ? page : "" };
  }

  function syncDeepLink() {
    if (!state.current) return;
    const url = new URL(location.href);
    url.searchParams.set("report", state.current);
    if (state.page) url.searchParams.set("page", state.page);
    else url.searchParams.delete("page");
    history.replaceState(null, "", url.pathname + url.search + url.hash);
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

  function outlineHtml() {
    const list = pages();
    if (!list.length || !state.current) {
      return (
        "<div class='bci-r-card'><h4>标准化报告大纲</h4>" +
        "<p class='bci-r-hint'>打开一个报告版本后，这里列出 11 页大纲，点哪页右侧只看哪页。</p></div>"
      );
    }
    const active = ensurePage();
    return (
      "<div class='bci-r-card bci-r-outline'>" +
      "<h4>标准化报告大纲<small>共 " +
      esc(list.length) +
      " 页</small></h4>" +
      "<ol class='bci-r-outline-list'>" +
      list
        .map(function (item) {
          return (
            "<li><button type='button' class='bci-r-outline-item" +
            (item.page === active ? " is-active" : "") +
            "' data-page='" +
            esc(item.page) +
            "'><b>" +
            esc(pageLabel(item.page)) +
            "</b><span>" +
            esc(String(item.title || "").replace(/^\d+-/, "")) +
            "</span></button></li>"
          );
        })
        .join("") +
      "</ol></div>"
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
    if (!state.detail) {
      return "<div class='bci-r-empty'>正在加载报告…</div>";
    }
    const detail = state.detail;
    const list = pages();
    const pageId = ensurePage();
    const index = pageIndex(pageId);
    const meta =
      esc(detail.version_label) +
      " · " +
      esc(when(detail.generated_at)) +
      " · " +
      (detail.revision_kind === "revise" ? "改稿" : "生成") +
      " · 指纹 " +
      esc(String((detail.content && detail.content.data_fingerprint) || "").slice(0, 12));
    const banner = detail.stale
      ? "<div class='bci-r-banner'>该版本已过期：" + esc(detail.stale_reason || "底层数据已变化") + "。请重新生成。</div>"
      : "";
    const compareBtn = detail.parent_version_id
      ? "<button type='button' class='bci-r-btn' data-action='compare'>与上一版对比</button>"
      : "";
    return (
      "<div class='bci-r-view'>" +
      "<div class='bci-r-view__head'>" +
      "<div class='bci-r-view__meta'><b>报告单页</b><br>" +
      meta +
      "</div>" +
      "<div class='bci-r-view__actions'>" +
      compareBtn +
      "<button type='button' class='bci-r-btn' data-action='download'>下载整篇 HTML</button>" +
      "<button type='button' class='bci-r-btn' data-action='regenerate'" +
      (state.busy ? " disabled" : "") +
      ">重新生成</button>" +
      "</div></div>" +
      banner +
      "<div class='bci-r-pager'>" +
      "<button type='button' class='bci-r-pager__btn' data-action='prev-page'" +
      (index <= 0 ? " disabled" : "") +
      ">上一页</button>" +
      "<span class='bci-r-pager__label' data-page-label>" +
      esc(pageCounter(pageId)) +
      "</span>" +
      "<button type='button' class='bci-r-pager__btn' data-action='next-page'" +
      (index >= list.length - 1 ? " disabled" : "") +
      ">下一页</button>" +
      "</div>" +
      "<iframe class='bci-r-frame' referrerpolicy='no-referrer' src='" +
      esc(pageSrc(pageId)) +
      "' title='" +
      esc(pageId + " " + pageTitleText(pageId)) +
      "'></iframe>" +
      "<p class='bci-r-footnote'>当前只渲染这一页；导出 HTML 仍是完整 " + esc(list.length) + " 页。</p>" +
      "</div>"
    );
  }

  function revisePages() {
    return pages();
  }

  function changeRows(changes) {
    const labels = { title: "标题", subtitle: "副标题", lead: "导语", note: "说明" };
    return (changes || [])
      .map(function (item) {
        const field = labels[item.field] || item.field;
        const name = item.block ? item.block + " · " + field : field;
        return (
          "<tr data-change='changed'><td>" +
          esc(name) +
          "</td><td>" +
          esc(item.before || "—") +
          "</td><td>" +
          esc(item.after || "—") +
          "</td></tr>"
        );
      })
      .join("");
  }

  function recordHtml() {
    const patch = state.detail && state.detail.patch;
    const items = (patch && patch.rewrites) || [];
    if (!items.length) return "";
    const item = items[items.length - 1];
    return (
      "<div class='bci-r-record'>" +
      "<h5>本次改稿记录<small>" +
      esc((item.target || {}).page || "") +
      "</small></h5>" +
      "<p class='bci-r-record__line'><span>原指令</span>" +
      esc(item.instruction || "") +
      "</p>" +
      (item.changes && item.changes.length
        ? "<table class='bci-r-diff__table'><thead><tr><th>字段</th><th>改前</th><th>改后</th></tr></thead><tbody>" +
          changeRows(item.changes) +
          "</tbody></table>"
        : "") +
      "<p class='bci-r-record__line'><span>refs</span>" +
      esc((item.refs || []).join("、") || "—") +
      "</p>" +
      (item.quote_refs && item.quote_refs.length
        ? "<p class='bci-r-record__line'><span>受访人</span>" + esc(item.quote_refs.join("、")) + "</p>"
        : "") +
      "</div>"
    );
  }

  function reviseHtml() {
    if (!state.detail) {
      return "<div class='bci-r-card'><h4>报告校核</h4><p class='bci-r-hint'>先打开一个版本，再对某一页下达修改指令。</p></div>";
    }
    const list = revisePages();
    const active = state.revise.page || ensurePage();
    return (
      "<div class='bci-r-card'>" +
      "<h4>报告校核<small>只落新版本，旧版不动</small></h4>" +
      "<p class='bci-r-hint'>对任意一页下达自然语言修改指令：标题、导语、板块文案、表格说明都能改。数字与引语必须指回本页数据，两次校验不过则拒绝该版本。</p>" +
      "<div class='bci-r-revise'>" +
      "<label class='bci-r-field'><span>改哪一页</span><select data-revise='page'>" +
      list
        .map(function (item) {
          return (
            "<option value='" +
            esc(item.page) +
            "'" +
            (active === item.page ? " selected" : "") +
            ">" +
            esc(item.page + " · " + String(item.title || "").replace(/^\d+-/, "")) +
            "</option>"
          );
        })
        .join("") +
      "</select></label>" +
      "<label class='bci-r-field'><span>修改指令</span><textarea data-revise='instruction' rows='3' maxlength='300' placeholder='例：把本页标题改得更精炼；把小结收敛为 3 条；补充竞品来源页引用'>" +
      esc(state.revise.instruction) +
      "</textarea></label>" +
      "<button type='button' class='bci-r-btn bci-r-btn--primary' data-action='revise'" +
      (state.busy ? " disabled" : "") +
      ">" +
      (state.busy ? "改稿中…" : "按指令生成新版本") +
      "</button>" +
      "</div>" +
      recordHtml() +
      "</div>"
    );
  }

  function compareHtml() {
    if (!state.compare) {
      return "<div class='bci-r-card'><h4>版本对比</h4><p class='bci-r-hint'>打开一个改稿版本后点击「与上一版对比」，按页面、内容块与行键并排显示变化。</p></div>";
    }
    const diff = state.compare;
    const pages = diff.pages.filter(function (page) {
      return page.changed;
    });
    const labels = { title: "标题", subtitle: "副标题", lead: "导语" };
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
                (page.field_changes && page.field_changes.length
                  ? "<table class='bci-r-diff__table'><tbody>" +
                    page.field_changes
                      .map(function (item) {
                        return (
                          "<tr data-change='changed'><td>" +
                          esc(labels[item.field] || item.field) +
                          "</td><td>" +
                          esc(item.before || "—") +
                          "</td><td>" +
                          esc(item.after || "—") +
                          "</td></tr>"
                        );
                      })
                      .join("") +
                    "</tbody></table>"
                  : "") +
                blocks
                  .map(function (block) {
                    const rows = (block.field_changes || []).concat(
                      (block.row_changes || []).map(function (row) {
                        return { field: row.key, before: row.before, after: row.after };
                      })
                    );
                    return (
                      "<div class='bci-r-diff__block'><b>" +
                      esc(block.id) +
                      "</b> " +
                      esc(block.title || "") +
                      (rows.length
                        ? "<table class='bci-r-diff__table'><tbody>" +
                          rows
                            .map(function (row) {
                              return (
                                "<tr data-change='changed'><td>" +
                                esc(row.field) +
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
      "<p>一个目标车型一份报告：左侧大纲选页、右侧只看这一页；校核助手按自然语言指令重写单页文案，落成 v1.1、v1.2，旧版不动。</p>" +
      "</div>" +
      "<div class='bci-r-top__actions'><span class='bci-r-hint' style='margin:0'>同步生成，约 20–30 秒</span></div>" +
      "</div>" +
      "<div class='bci-r-grid'>" +
      "<div class='bci-r-stack'>" +
      outlineHtml() +
      configHtml() +
      "</div>" +
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

  // ------------------------------------------------------------ 数据加载

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

  async function openVersion(id, pageId) {
    state.current = id;
    state.detail = null;
    state.compare = null;
    if (pageId) state.page = pageId;
    render();
    try {
      state.detail = await api("/api/bci/report/detail?id=" + encodeURIComponent(id));
      if (state.detail.model_key && state.detail.model_key !== state.selected) {
        state.selected = state.detail.model_key;
        await loadVersions();
      }
      state.page = pickPage(state.page);
      state.revise.page = state.page;
      syncDeepLink();
      render();
    } catch (err) {
      state.status = { kind: "error", text: err.message };
      render();
    }
  }

  function setPage(pageId) {
    if (!pageId || pageId === state.page) return;
    state.page = pageId;
    state.revise.page = pageId;
    syncDeepLink();
    if (!state.host) return;
    const index = pageIndex(pageId);
    const total = pages().length;
    state.host.querySelectorAll("[data-page]").forEach(function (node) {
      node.classList.toggle("is-active", node.getAttribute("data-page") === pageId);
    });
    const label = state.host.querySelector("[data-page-label]");
    if (label) label.textContent = pageCounter(pageId);
    const frame = state.host.querySelector(".bci-r-frame");
    if (frame) frame.src = pageSrc(pageId);
    const select = state.host.querySelector("select[data-revise='page']");
    if (select) select.value = pageId;
    const prev = state.host.querySelector("[data-action='prev-page']");
    if (prev) prev.disabled = index <= 0;
    const next = state.host.querySelector("[data-action='next-page']");
    if (next) next.disabled = index >= total - 1;
  }

  function stepPage(delta) {
    const list = pages();
    const index = pageIndex(state.page);
    const target = list[index + delta];
    if (target) setPage(target.page);
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
    const page = state.revise.page || ensurePage();
    const instruction = String(state.revise.instruction || "").trim();
    if (!instruction) {
      setStatus("error", "请先写下这一页要改什么。");
      return;
    }
    state.busy = true;
    state.status = { kind: "", text: "正在按指令改写 " + page + "，并校验数字与引语溯源…" };
    render();
    try {
      const data = await api("/api/bci/report/revise", {
        method: "POST",
        body: JSON.stringify({
          report_version_id: state.current,
          operations: [{ op: "rewrite_page", target: { page: page }, instruction: instruction }],
        }),
      });
      await loadVersions();
      state.busy = false;
      state.page = page;
      state.revise.instruction = "";
      await openVersion(data.report_version_id, page);
      state.status = { kind: "ok", text: "已生成 " + data.version_label + "，父版本保持不变；改稿记录见下方。" };
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
    state.host.addEventListener(
      "load",
      function (ev) {
        const frame = ev.target;
        if (!frame.classList || !frame.classList.contains("bci-r-frame")) return;
        try {
          const doc = frame.contentDocument;
          if (!doc) return;
          const height = Math.min(Math.max(doc.documentElement.scrollHeight, 420), 1600);
          frame.style.height = height + "px";
        } catch (err) {
          /* 跨源时保持默认高度 */
        }
      },
      true
    );
    state.host.addEventListener("input", function (ev) {
      const field = ev.target.closest("[data-revise='instruction']");
      if (field) state.revise.instruction = field.value;
    });
    state.host.addEventListener("change", function (ev) {
      const radio = ev.target.closest("input[data-model]");
      if (radio) {
        state.selected = radio.getAttribute("data-model");
        state.current = null;
        state.detail = null;
        state.compare = null;
        state.status = null;
        state.page = "";
        state.revise.page = "";
        loadVersions()
          .then(function () {
            return state.versions.length ? openVersion(state.versions[0].report_version_id) : render();
          })
          .catch(function (err) {
            setStatus("error", err.message);
          });
        return;
      }
      const field = ev.target.closest("select[data-revise='page']");
      if (field) {
        state.revise.page = field.value;
        setPage(field.value);
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
        if (name === "prev-page") stepPage(-1);
        if (name === "next-page") stepPage(1);
        return;
      }
      const page = ev.target.closest("[data-page]");
      if (page) {
        setPage(page.getAttribute("data-page"));
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
    const deep = readDeepLink();
    try {
      await loadOptions();
      await loadVersions();
      bind();
      if (deep && deep.version) {
        await openVersion(deep.version, deep.page);
      } else if (state.versions.length) {
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
