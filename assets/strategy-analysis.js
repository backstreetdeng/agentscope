(function () {
  "use strict";

  const $ = (id) => document.getElementById(id);
  const DEFAULT_QUESTION = "请启动乘用车月报后台任务并立即返回run_id。先检查已登录的数据源，按批次读取并保存全部映射卡片；针对异常对象优先调用政策、权益、新车、口碑插件取证，必要时用Tavily补充公开证据。完成标准化、多源交叉校验、异常识别和逐页主旨句证据包后返回分析结果，并启用右侧“生成PPT版”。用户点击后必须携带同一run_id，从检查点读取已验收的数据包和证据包，基于最新版兼容模板执行一次确定性PPT更新。每批保存检查点并上报真实进度；页面刷新、服务重启或单次读取超时时从最近检查点恢复，不得重采已完成批次、沿用上月数据或补造结论。";
  const LEGACY_MONTHLY_QUESTION = "请读取已登录的乘用车月报数据源，按当前报告月份提取并校验全部映射数据，基于最新版兼容模板生成中国乘用车市场月度分析报告PPT。先完成数据快照、完整性检查和PPT数据更新，再生成各页主旨句；如数据未更新、存在缺失或口径不一致，请停止正式生成并列出异常，不得沿用上月数据或补造结论。";
  const LEGACY_MACRO_QUESTION = "请读取已上传的宏观经济月报标准台账，按当前报告月份识别并校验GDP、PMI、CPI、PPI、消费、投资、进出口、金融等宏观指标，基于宏观经济月报固定模板生成当月宏观经济分析报告PPT。先完成台账结构识别、月份覆盖检查、指标口径与来源校验，再更新模板中的可编辑图表、表格和结论；如数据缺失、月份未更新或口径不一致，请停止正式生成并列出异常，不得沿用上月数据、填入未来零值或补造结论。";
  const GENERAL_QUESTION = "请根据当前问题开展汽车市场分析，只调用我已勾选的技能与插件，并说明实际使用了哪些能力。";
  const INITIAL_LOG = "等待执行...\n[22:41:18] skill-task: 乘用车月报智能生成 已填入任务问题";
  const MACRO_INITIAL_LOG = "等待执行...\n[22:41:18] skill-task: 宏观经济月报 已填入任务问题\n[22:41:18] audit-ledger: 将在执行时自动建立逐页核对台账";
  const GENERAL_INITIAL_LOG = "等待执行...\n未选择月报技能，将按当前问题与已选能力执行通用市场分析。";
  const ACTIVE_MONTHLY_RUN_KEY = "passenger-car-monthly-active-run";
  const ACTIVE_MACRO_RUN_KEY = "macro-monthly-active-run";
  const LAST_MACRO_DRAFT_KEY = "macro-monthly-last-public-draft-run";

  const capabilities = [
    {
      group: "技能",
      items: [
        ["passenger_car_monthly_report", "乘用车月报智能生成", "数据源读取、映射验数、21页PPT与主旨句生成", false],
        ["macro_monthly_report", "宏观经济月报", "指定月份直接执行，自动取数并更新33页可编辑月报", false]
      ]
    },
    {
      group: "插件",
      items: [
        ["policy", "政策数据底座", "政策原文、时间窗与影响范围", true],
        ["rights", "权益数据底座", "官方权益、金融与置换补贴", true],
        ["newcar", "新车数据底座", "上市公告、配置、定价与权益", true],
        ["reputation", "口碑数据底座", "评论聚合、标签与情感打分", true]
      ]
    }
  ];

  const mcpPluginByCapability = {
    policy: "policy",
    rights: "rights",
    newcar: "new-car",
    reputation: "reputation"
  };

  const stageModel = [
    ["intent", "意图识别"],
    ["tools", "工具与证据准备"],
    ["reasoning", "业务框架推理"],
    ["quality", "数据质量门禁"],
    ["report", "报告生成"]
  ];

  const state = {
    running: false,
    lastReport: "",
    lastQuality: null,
    lastMeta: null,
    progressTimer: null,
    narrativeTimer: null,
    toastTimer: null,
    activeRunId: null,
    lastJobEventSeq: 0
  };

  function escapeHtml(value) {
    return String(value == null ? "" : value)
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;")
      .replaceAll("'", "&#39;");
  }

  function showToast(message) {
    const toast = $("toast");
    toast.textContent = message;
    toast.hidden = false;
    window.clearTimeout(state.toastTimer);
    state.toastTimer = window.setTimeout(() => { toast.hidden = true; }, 2600);
  }

  function setConnection(kind, text) {
    const pill = $("connectionPill");
    pill.classList.remove("is-error", "is-running");
    if (kind === "error") pill.classList.add("is-error");
    if (kind === "running") pill.classList.add("is-running");
    $("connectionText").textContent = text;
  }

  function renderCapabilities() {
    const params = new URLSearchParams(window.location.search);
    const requested = new Set(
      [params.get("skills"), params.get("plugins")]
        .filter(Boolean)
        .flatMap((value) => value.split(","))
        .map((value) => value.trim())
        .filter(Boolean)
    );
    $("capabilityList").innerHTML = capabilities.map((section) => `
      <section class="capability-group">
        <h4>${escapeHtml(section.group)}</h4>
        ${section.items.map(([id, name, desc, checked]) => `
          <label class="capability-option">
            <input type="checkbox" value="${escapeHtml(id)}" ${(requested.has(id) || checked) ? "checked" : ""}>
            <span><strong>${escapeHtml(name)}</strong><p>${escapeHtml(desc)}</p></span>
            <em>${escapeHtml(section.group)}</em>
          </label>
        `).join("")}
      </section>
    `).join("");
    if (requested.has("macro_monthly_report")) {
      const passenger = $("capabilityList").querySelector('input[value="passenger_car_monthly_report"]');
      if (passenger) passenger.checked = false;
    }
    $("capabilityList").querySelectorAll("input").forEach((input) => {
      input.addEventListener("change", () => {
        enforceMonthlySkillExclusivity(input);
        updateCapabilitySummary();
      });
    });
    updateCapabilitySummary();
  }

  function enforceMonthlySkillExclusivity(changedInput) {
    if (!changedInput.checked || !["passenger_car_monthly_report", "macro_monthly_report"].includes(changedInput.value)) return;
    const otherId = changedInput.value === "macro_monthly_report" ? "passenger_car_monthly_report" : "macro_monthly_report";
    const other = $("capabilityList").querySelector(`input[value="${otherId}"]`);
    if (other) other.checked = false;
  }

  function selectedCapabilities() {
    return Array.from($("capabilityList").querySelectorAll("input:checked")).map((input) => input.value);
  }

  function selectedMcpPlugins(selected) {
    return selected.map((id) => mcpPluginByCapability[id]).filter(Boolean);
  }

  function updateCapabilitySummary() {
    const selected = selectedCapabilities();
    $("capabilityCount").textContent = String(selected.length);
    $("capabilityHint").textContent = selected.length
      ? `已选择 ${selected.length} 项能力，运行时按任务编排`
      : "未选择能力，系统将使用基础分析链路";
    syncMacroRunConfig();
    syncTaskPreset();
  }

  function macroReportMonthLabel() {
    const value = $("macroReportMonth").value;
    if (!/^\d{4}-\d{2}$/.test(value)) return "所选报告月份";
    const [year, month] = value.split("-");
    return `${year}年${Number(month)}月`;
  }

  function macroQuestion() {
    return `请使用宏观经济月报技能，为${macroReportMonthLabel()}生成经济分析报告。延续历史图表，补采新月份数据，从已核验事实提炼主题句并单独展望下月。某页数据无法更新时，保留模板历史数据和原统计日期，明确标注“暂无可核验数据”。有未更新页则为部分完成；所有页均有数据支持后才算完成。保存缺项页清单，下次继续任务时仅补采这些页，复用已采集的数据。`;
  }

  function macroDraftRequestFields(selected, checked) {
    return Array.isArray(selected) && selected.includes("macro_monthly_report") && checked === true
      ? { delivery_mode: "public_draft", public_draft_confirmed: true }
      : {};
  }

  function macroDraftDelivery(data, analysisType) {
    const skillRun = data && data.skill_run;
    const runState = skillRun && skillRun.state;
    const runId = data && (data.run_id || (skillRun && skillRun.run_id));
    const url = data && (data.draft_delivery_url || (skillRun && skillRun.delivery_url));
    const mode = data && (data.delivery_mode || (skillRun && skillRun.delivery_mode) || (runState && runState.delivery_mode));
    const isDraft = analysisType === "macro_monthly_report" && mode === "public_draft";
    const expected = /^macro-[a-zA-Z0-9-]+$/.test(runId || "") ? `/api/macro-report/draft/${runId}` : "";
    const ready = isDraft && data.draft_delivery_allowed === true && data.formal_delivery_allowed === false
      && data.business_status === "draft_passed" && runState && runState.draft_validation
      && runState.draft_validation.status === "passed"
      && runState.status === "draft_ready" && (!data.job_status || data.job_status === "draft_ready")
      && (!skillRun.run_id || skillRun.run_id === runId) && Boolean(expected) && url === expected;
    return { isDraft, ready: Boolean(ready), url: ready ? url : "", runId };
  }

  function macroRetainedDelivery(data, analysisType) {
    const skillRun = data && data.skill_run;
    const runState = skillRun && skillRun.state;
    const runId = data && (data.run_id || (skillRun && skillRun.run_id));
    const url = data && (data.retained_delivery_url || (skillRun && skillRun.delivery_url));
    const mode = data && (data.delivery_mode || (skillRun && skillRun.delivery_mode) || (runState && runState.delivery_mode));
    const isRetained = analysisType === "macro_monthly_report" && mode === "historical_retained";
    const expected = /^macro-[a-zA-Z0-9-]+$/.test(runId || "") ? `/api/macro-report/retained/${runId}` : "";
    const ready = isRetained && data.retained_delivery_allowed === true && data.formal_delivery_allowed === false
      && data.business_status === "retained_passed" && runState && runState.retained_validation
      && runState.retained_validation.status === "passed"
      && ["completed", "partial_completed", "retained_ready"].includes(runState.status) && (!data.job_status || ["completed", "partial_completed", "retained_ready"].includes(data.job_status))
      && (!skillRun.run_id || skillRun.run_id === runId) && Boolean(expected) && url === expected;
    return { isRetained, ready: Boolean(ready), url: ready ? url : "", runId };
  }

  function macroFormalDelivery(data) {
    const runtime = data && data.skill_run;
    const runState = runtime && runtime.state;
    const runId = data && (data.run_id || (runtime && runtime.run_id));
    const url = runtime && runtime.delivery_url;
    let decoded = "";
    try { decoded = typeof url === "string" ? decodeURIComponent(url) : ""; } catch (_) {}
    const gates = new Set((runState && Array.isArray(runState.artifact_validations) ? runState.artifact_validations : [])
      .filter(item => item.passed === true).map(item => item.validator));
    const ready = /^macro-\d{8}-\d{6}-[a-f0-9]{8}$/.test(runId || "")
      && data.job_status === "completed" && data.business_status === "passed" && data.formal_delivery_allowed === true
      && runtime && runtime.run_id === runId && runState && runState.business_status === "passed"
      && runState.formal_delivery_allowed === true && runState.validation && runState.validation.status === "passed"
      && ["macro_business", "pptx_structure", "powerpoint_render", "macro_layout"].every(gate => gates.has(gate))
      && decoded.startsWith(`/outputs/ppt/${runId}-`) && /^\/outputs\/ppt\/[^\\/?#]+\.pptx$/.test(decoded);
    return { ready: Boolean(ready), url: ready ? url : "", runId };
  }

  function syncTaskPreset(force) {
    const monthlyEnabled = selectedCapabilities().includes("passenger_car_monthly_report");
    const macroEnabled = selectedCapabilities().includes("macro_monthly_report");
    const desiredQuestion = macroEnabled ? macroQuestion() : monthlyEnabled ? DEFAULT_QUESTION : GENERAL_QUESTION;
    const currentQuestion = $("questionInput").value.trim();
    const previousPreset = $("questionInput").dataset.systemPreset || "";
    const isSystemPreset = !currentQuestion || currentQuestion === previousPreset || [DEFAULT_QUESTION, LEGACY_MONTHLY_QUESTION, LEGACY_MACRO_QUESTION, GENERAL_QUESTION].includes(currentQuestion);
    if (force || isSystemPreset) {
      $("questionInput").value = desiredQuestion;
      $("questionInput").dataset.systemPreset = desiredQuestion;
    }
    $("assistantStatus").textContent = macroEnabled
      ? "已装载宏观经济月报能力。选择报告月份即可直接执行；逐页数据台账由智能体内部自动建立。"
      : monthlyEnabled
        ? "已装载乘用车月报智能生成能力。请确认月报数据源已刷新并保持登录后开始分析。"
        : "未选择月报技能。系统只会调用当前勾选的技能与插件执行通用市场分析。";
    if (!state.running && !state.lastReport) {
      $("eventLog").textContent = macroEnabled ? MACRO_INITIAL_LOG : monthlyEnabled ? INITIAL_LOG : GENERAL_INITIAL_LOG;
    }
  }

  function syncMacroRunConfig() {
    const enabled = selectedCapabilities().includes("macro_monthly_report");
    $("macroRunConfig").hidden = !enabled;
    const passengerEnabled = selectedCapabilities().includes("passenger_car_monthly_report");
    $("passengerRunConfig").hidden = !passengerEnabled;
    $("passengerRunSummary").hidden = !passengerEnabled;
  }

  function toggleCapabilities(force) {
    const popover = $("capabilityPopover");
    const open = typeof force === "boolean" ? force : popover.hidden;
    popover.hidden = !open;
    $("capabilityTrigger").setAttribute("aria-expanded", String(open));
  }

  function initSteps() {
    $("steps").innerHTML = stageModel.map(([id, name]) => `
      <div class="step" id="step-${id}">
        <span class="step-dot" aria-hidden="true"></span>
        <div class="step-copy"><strong>${name}</strong><p id="summary-${id}">-</p></div>
        <span class="step-status" id="status-${id}">待执行</span>
      </div>
    `).join("");
  }

  function updateStep(id, status, summary) {
    const row = $("step-" + id);
    if (!row) return;
    row.classList.remove("running", "done", "blocked");
    if (status === "running") row.classList.add("running");
    if (status === "done") row.classList.add("done");
    if (status === "blocked") row.classList.add("blocked");
    $("status-" + id).textContent = status === "blocked" ? "阻断" : status === "done" ? "完成" : status === "running" ? "执行中" : "待执行";
    if (summary) $("summary-" + id).textContent = summary;
  }

  function setProgress(value) {
    $("progressFill").style.width = `${Math.max(0, Math.min(100, value))}%`;
  }

  function setExecutionState(kind, text) {
    const label = $("executionState");
    label.className = "execution-state" + (kind ? ` ${kind}` : "");
    label.textContent = text;
  }

  function appendLog(message) {
    const time = new Date().toLocaleTimeString("zh-CN", { hour12: false });
    const log = $("eventLog");
    log.textContent += `\n[${time}] ${message}`;
    log.scrollTop = log.scrollHeight;
  }

  function startNarrative(modelLabel, monthlyEnabled) {
    stopNarrative();
    const plan = monthlyEnabled ? [
      [900, "tools", "running", "正在读取已验证的月报数据包或进行轻量页面检查。", 23, "source-check: 正在检查数据包与页面连接"],
      [3600, "tools", "running", "正在核对45张卡片的映射与月份。", 43, "mapping-check: 正在核对卡片映射"],
      [8200, "quality", "running", "正在检查数据完整性与口径一致性。", 64, "quality: 数据质量门禁执行中"],
      [14500, "report", "running", "数据通过后将进入确定性PPT更新。", 78, "delivery: 等待数据包处理完成"]
    ] : [
      [900, "tools", "running", `已装载 ${modelLabel} 与当前勾选的能力。`, 23, "tool-prepare: 模型、技能与插件清单已就绪"],
      [3600, "reasoning", "running", "正在根据当前问题组织市场分析框架。", 43, "framework: 正在组织可核对的业务分析路径"],
      [8200, "quality", "running", "正在准备数据完整性、口径与证据一致性检查。", 64, "quality: 数据质量门禁准备中"],
      [14500, "report", "running", "正在生成分析报告。", 78, "report: 等待模型返回完整报告"]
    ];
    const started = Date.now();
    let index = 0;
    let heartbeat = 0;
    state.narrativeTimer = window.setInterval(() => {
      const elapsed = Date.now() - started;
      while (index < plan.length && elapsed >= plan[index][0]) {
        const [, id, status, summary, progress, log] = plan[index];
        updateStep(id, status, summary);
        setProgress(progress);
        appendLog(log);
        index += 1;
      }
      if (elapsed > 22000 && elapsed - heartbeat > 12000) {
        heartbeat = elapsed;
        appendLog(`heartbeat: ${monthlyEnabled ? "数据源采集与映射核对" : "智能体"}仍在执行，已耗时 ${Math.round(elapsed / 1000)} 秒`);
      }
    }, 700);
  }

  function stopNarrative() {
    if (state.narrativeTimer) window.clearInterval(state.narrativeTimer);
    state.narrativeTimer = null;
  }

  function addUserMessage(question) {
    const old = $("conversationStream").querySelector(".user-message");
    if (old) old.remove();
    const message = document.createElement("div");
    message.className = "user-message";
    message.innerHTML = `<div><span>本轮任务</span><p>${escapeHtml(question)}</p></div>`;
    const execution = $("conversationStream").querySelector(".execution-card");
    execution.parentNode.insertBefore(message, execution);
    $("conversationStream").scrollTop = 0;
  }

  function setRunning(running) {
    state.running = running;
    $("runBtn").disabled = running;
    $("runBtn").innerHTML = `<span>${running ? "分析中" : "开始分析"}</span><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M5 12h14M13 6l6 6-6 6"/></svg>`;
    $("questionInput").disabled = running;
    $("modelSelect").disabled = running;
    $("capabilityTrigger").disabled = running;
    $("macroReportMonth").disabled = running;
    $("passengerReportMonth").disabled = running;
    $("cancelRunBtn").hidden = !(running && state.activeRunId);
    $("cancelRunBtn").disabled = false;
  }

  function rememberMonthlyRun(runId) {
    const key = (runId || state.activeRunId || "").startsWith("macro-") ? ACTIVE_MACRO_RUN_KEY : ACTIVE_MONTHLY_RUN_KEY;
    state.activeRunId = runId || null;
    state.lastJobEventSeq = 0;
    if (runId) {
      window.localStorage.setItem(key, runId);
      // Refresh restores this tab's run, not another tab's most recent draft.
      const params = new URLSearchParams(window.location.search);
      params.delete("new");
      params.set("run", runId);
      window.history.replaceState(null, "", `${window.location.pathname}?${params.toString()}${window.location.hash || ""}`);
    } else window.localStorage.removeItem(key);
    $("cancelRunBtn").hidden = !(state.running && state.activeRunId);
  }

  function phaseStep(phase) {
    if (["queued", "start"].includes(phase)) return "intent";
    if (["preflight", "data_collect"].includes(phase)) return "tools";
    if (["data_gate", "narrative"].includes(phase)) return "quality";
    if (["result_prepare", "archive", "completed", "retained_ready", "draft_ready"].includes(phase)) return "report";
    if (["inventory", "sources"].includes(phase)) return "tools";
    if (["typed_update", "normalize", "forecast", "chart_update", "narrative", "business_gate"].includes(phase)) return "quality";
    if (["structure_gate", "office_gate", "finalize"].includes(phase)) return "report";
    return "tools";
  }

  function applyMonthlyJobEvent(event) {
    if (!event || Number(event.seq || 0) <= state.lastJobEventSeq) return;
    state.lastJobEventSeq = Number(event.seq || 0);
    const time = event.at ? new Date(event.at).toLocaleTimeString("zh-CN", { hour12: false }) : new Date().toLocaleTimeString("zh-CN", { hour12: false });
    const log = $("eventLog");
    log.textContent += `\n[${time}] ${event.phase}: ${event.message}`;
    log.scrollTop = log.scrollHeight;
    setProgress(Number(event.progress || 0));
    const step = phaseStep(event.phase);
    if (step === "tools") updateStep("tools", "running", event.message);
    if (step === "quality") {
      updateStep("tools", "done", "数据源读取和标准化数据包已完成。");
      const reasoning = ["narrative", "typed_update", "normalize", "forecast", "chart_update", "business_gate"].includes(event.phase);
      updateStep("reasoning", reasoning ? "running" : "waiting", reasoning ? event.message : "正在校验月份与数据完整性，业务分析尚未执行。");
      updateStep("quality", "running", event.message);
    }
    if (step === "report") {
      if (["completed", "retained_ready", "draft_ready", "result_prepare"].includes(event.phase)) updateStep("quality", "done", "本轮阶段验收已通过。");
      updateStep("report", ["completed", "partial_completed", "retained_ready", "draft_ready"].includes(event.phase) ? "done" : "running", event.message);
    }
    setConnection("running", `月报后台执行 · ${event.progress || 0}%`);
  }

  function enableResultActions(enabled) {
    ["copyBtn", "pptBtn", "downloadBtn"].forEach((id) => { $(id).disabled = !enabled; });
  }

  function emptyReport(title, detail, action) {
    $("reportArea").innerHTML = `
      <div class="empty-state">
        <span class="empty-visual" aria-hidden="true"><svg viewBox="0 0 64 64"><path d="M18 8h22l10 10v38H18z"/><path d="M40 8v12h12M25 30h18M25 38h18M25 46h11"/></svg></span>
        <strong>${escapeHtml(title)}</strong><p>${escapeHtml(detail)}</p>
        ${action ? `<button id="dynamicEmptyButton" type="button">${escapeHtml(action)}</button>` : ""}
      </div>`;
  }

  function formatInline(text) {
    return text
      .replace(/\*\*(.*?)\*\*/g, "<strong>$1</strong>")
      .replace(/`([^`]+)`/g, "<code>$1</code>");
  }

  function markdownToHtml(markdown) {
    const safe = escapeHtml(markdown || "");
    const lines = safe.split(/\r?\n/);
    let html = "";
    let inTable = false;
    let inList = false;
    for (const raw of lines) {
      const line = raw.trimEnd();
      if (/^\|.+\|$/.test(line.trim())) {
        if (inList) { html += "</ul>"; inList = false; }
        const cells = line.trim().slice(1, -1).split("|").map((cell) => cell.trim());
        if (cells.every((cell) => /^:?-{3,}:?$/.test(cell))) continue;
        if (!inTable) { html += "<table>"; inTable = true; }
        html += "<tr>" + cells.map((cell) => `<td>${formatInline(cell)}</td>`).join("") + "</tr>";
        continue;
      }
      if (inTable) { html += "</table>"; inTable = false; }
      const listMatch = line.match(/^[-*]\s+(.+)/);
      if (listMatch) {
        if (!inList) { html += "<ul>"; inList = true; }
        html += `<li>${formatInline(listMatch[1])}</li>`;
        continue;
      }
      if (inList) { html += "</ul>"; inList = false; }
      if (/^###\s+/.test(line)) html += `<h3>${formatInline(line.replace(/^###\s+/, ""))}</h3>`;
      else if (/^##\s+/.test(line)) html += `<h2>${formatInline(line.replace(/^##\s+/, ""))}</h2>`;
      else if (/^#\s+/.test(line)) html += `<h1>${formatInline(line.replace(/^#\s+/, ""))}</h1>`;
      else if (/^&gt;\s+/.test(line)) html += `<blockquote>${formatInline(line.replace(/^&gt;\s+/, ""))}</blockquote>`;
      else if (line.trim()) html += `<p>${formatInline(line)}</p>`;
    }
    if (inTable) html += "</table>";
    if (inList) html += "</ul>";
    return html;
  }

  function qualityClass(status) {
    if (status === "通过") return "pass";
    if (status === "草稿验收通过") return "warn";
    if (["待核验", "待补充", "警告"].includes(status)) return "warn";
    if (["风险", "阻断", "失败"].includes(status)) return "fail";
    return "";
  }

  function renderQuality(data) {
    state.lastQuality = data;
    const status = data.overall_status || "待核验";
    $("qualityMetric").textContent = status;
    $("qualityMetric").style.color = status === "通过" ? "var(--green)" : ["风险", "阻断"].includes(status) ? "var(--red)" : "var(--orange)";
    $("qualityPanel").innerHTML = `
      <div>
        <span class="quality-mark" aria-hidden="true"><svg viewBox="0 0 24 24"><path d="M12 3 4.5 6v5.3c0 4.6 3.2 8.2 7.5 9.7 4.3-1.5 7.5-5.1 7.5-9.7V6z"/><path d="m9 12 2 2 4-4"/></svg></span>
        <div><h3>${escapeHtml(data.title || "数据质量门禁")}</h3><p>${escapeHtml(data.impact || "报告已完成自动质量审查。")}</p></div>
      </div>
      <span class="quality-status ${qualityClass(status)}">${escapeHtml(status)}${data.score != null ? ` · ${Number(data.score)}/100` : ""}</span>
      ${(data.checks || []).length ? `<div class="quality-details" style="flex-basis:100%"><div class="quality-grid">${data.checks.map((item) => `
        <div class="quality-check"><div><strong>${escapeHtml(item.name)}</strong><em>${escapeHtml(item.status)}</em></div><p>${escapeHtml(item.evidence || item.suggestion || "")}</p></div>
      `).join("")}</div></div>` : ""}`;
    $("qualityPanel").style.flexWrap = "wrap";
  }

  async function evaluateQuality(report, question, toolEvents) {
    const response = await fetch("/api/quality-gate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ report, question, tool_events: toolEvents || [] })
    });
    const data = await response.json();
    if (!response.ok || data.error) throw new Error(data.error || `质量门禁返回 HTTP ${response.status}`);
    renderQuality(data);
    return data;
  }

  function renderInitialQuality() {
    $("qualityPanel").style.flexWrap = "nowrap";
    $("qualityPanel").innerHTML = `
      <div>
        <span class="quality-mark" aria-hidden="true"><svg viewBox="0 0 24 24"><path d="M12 3 4.5 6v5.3c0 4.6 3.2 8.2 7.5 9.7 4.3-1.5 7.5-5.1 7.5-9.7V6z"/><path d="m9 12 2 2 4-4"/></svg></span>
        <div><h3>数据质量门禁</h3><p>报告返回后自动审查；状态会影响 PPT 生成提醒。</p></div>
      </div><span class="quality-status" id="qualityStatus">待报告生成</span>`;
  }

  function wait(ms) {
    return new Promise((resolve) => window.setTimeout(resolve, ms));
  }

  function errorMessage(value, fallback) {
    if (typeof value === "string" && value.trim()) return value;
    if (value && typeof value === "object") {
      if (typeof value.message === "string" && value.message.trim()) return value.message;
      if (typeof value.detail === "string" && value.detail.trim()) return value.detail;
    }
    return fallback;
  }

  async function requestJson(url, options, allowErrorPayload = false) {
    let response;
    try {
      response = await fetch(url, options);
    } catch (cause) {
      const error = new Error(errorMessage(cause, "无法连接后端服务"));
      error.isNetworkError = true;
      error.cause = cause;
      throw error;
    }
    let data;
    try {
      data = await response.json();
    } catch (cause) {
      const error = new Error(`服务返回了不可解析的响应（HTTP ${response.status}）`);
      error.httpStatus = response.status;
      error.isNetworkError = [502, 503, 504].includes(response.status);
      error.cause = cause;
      throw error;
    }
    if (!response.ok || (!allowErrorPayload && data.error)) {
      const error = new Error(errorMessage(data.error, `服务返回 HTTP ${response.status}`));
      error.httpStatus = response.status;
      error.isNetworkError = [502, 503, 504].includes(response.status);
      throw error;
    }
    return data;
  }

  function isTransientMonthlyPollError(error) {
    if (!error) return false;
    if (error.isNetworkError) return true;
    if ([502, 503, 504].includes(Number(error.httpStatus))) return true;
    return /failed to fetch|networkerror|load failed|无法连接后端服务/i.test(String(error.message || ""));
  }

  function backgroundJobApi(runId) {
    return String(runId || "").startsWith("macro-") ? macroApiUrl("/api/macro-report/jobs") : "/api/monthly-report/jobs";
  }

  function macroApiUrl(path) {
    // Keep the authenticated monthly-report service running while the updated
    // macro executor uses its isolated local Office-capable worker.
    return window.location.port === "7860" && ["127.0.0.1","localhost"].includes(window.location.hostname)
      ? `http://127.0.0.1:7861${path}` : path;
  }

  async function fetchMonthlyJobSnapshot(runId) {
    let failureCount = 0;
    while (true) {
      try {
        const job = await requestJson(
          `${backgroundJobApi(runId)}/${encodeURIComponent(runId)}`,
          { cache: "no-store" },
          true
        );
        if (failureCount > 0) {
          appendLog(`reconnect: 后端连接已恢复，继续读取 ${runId} 的检查点`);
          setConnection("running", "后台连接已恢复");
        }
        return job;
      } catch (error) {
        if (!isTransientMonthlyPollError(error)) throw error;
        failureCount += 1;
        setExecutionState("running", "后台服务重连中");
        setConnection("running", "连接中断，自动重连中");
        if (failureCount === 1) {
          appendLog(`reconnect: 后端连接暂时中断，已保留 run_id=${runId}，正在自动重连`);
        } else if (failureCount % 10 === 0) {
          appendLog(`reconnect: 已重试 ${failureCount} 次；任务检查点仍保留，不会重新创建任务`);
        }
        await wait(Math.min(1500 + failureCount * 250, 5000));
      }
    }
  }

  function renderPassengerRunSummary(job) {
    if (!job || String(job.run_id || "").startsWith("macro-")) return;
    const result = job.result || job;
    const source = result.skill && result.skill.source_package || {};
    const preflight = result.preflight || {};
    const month = job.report_month || source.report_month || preflight.report_month || "";
    const mode = job.collection_mode || source.collection_mode || preflight.collection_mode || "";
    const labels = {awaiting_month: "等待明确月份，尚未采集", waiting_source: "等待数据源就绪", reuse: "复用已有数据", partial_collect: "仅补采未通过项", collect: "采集目标月份数据", force_refresh: "按明确要求重新采集"};
    const reused = job.cards_reused ?? source.cards_reused ?? preflight.cards_reused;
    const collected = job.cards_collected ?? source.cards_collected ?? preflight.cards_collected;
    const decision = job.reuse_decision || source.reuse_decision || preflight.reuse_decision || {};
    const reason = typeof decision === "string" ? decision : decision.message || "";
    const parts = [`报告月份：${month || "待预检确认"}`, `处理方式：${labels[mode] || "待核验复用条件"}`];
    if (reused != null) parts.push(`已复用 ${reused} 张`);
    if (collected != null) parts.push(`本次采集 ${collected} 张`);
    if (reason) parts.push(reason);
    $("passengerRunSummary").textContent = parts.join("；");
    $("passengerRunSummary").hidden = false;
  }

  async function pollMonthlyJob(runId) {
    while (true) {
      const job = await fetchMonthlyJobSnapshot(runId);
      if (!runId.startsWith("macro-")) renderPassengerRunSummary(job);
      (Array.isArray(job.events) ? job.events : []).forEach(applyMonthlyJobEvent);
      if (["completed", "partial_completed", "retained_ready", "draft_ready"].includes(job.status)) {
        const result = job.result || {};
        result.run_id = runId;
        result.job_status = job.status;
        rememberMonthlyRun(null);
        if (job.status === "draft_ready") window.localStorage.setItem(LAST_MACRO_DRAFT_KEY, runId);
        return result;
      }
      if (["failed", "cancelled", "input_required", "waiting_input", "needs_repair"].includes(job.status)) {
        const message = job.message || (job.error && job.error.message) || "月报后台任务未完成。";
        const error = new Error(message);
        error.runId = runId;
        error.recoverable = Boolean(job.recoverable);
        error.jobStatus = job.status;
        error.result = job.result || null;
        error.issues = job.error && Array.isArray(job.error.issues) ? job.error.issues : [];
        error.preflight = job.result && job.result.preflight ? job.result.preflight : null;
        const source = error.result && error.result.skill && error.result.skill.source_package || {};
        error.code = (error.preflight && error.preflight.code) || source.code || (job.error && job.error.type) ||
          (job.status === "cancelled" ? "monthly_job_cancelled" : "monthly_job_failed");
        throw error;
      }
      await wait(1500);
    }
  }

  async function startMonthlyBackgroundJob(payload) {
    const job = await requestJson(payload.analysis_type === "macro_monthly_report" ? macroApiUrl("/api/macro-report/jobs") : "/api/monthly-report/jobs", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    });
    window.localStorage.removeItem(LAST_MACRO_DRAFT_KEY);
    rememberMonthlyRun(job.run_id);
    if (!job.run_id.startsWith("macro-")) renderPassengerRunSummary(job);
    setRunning(true);
    appendLog(`run-id: ${job.run_id} / 已转入后台执行`);
    (Array.isArray(job.events) ? job.events : []).forEach(applyMonthlyJobEvent);
    return pollMonthlyJob(job.run_id);
  }

  async function resumeMonthlyJob(runId, context) {
    if (!runId || state.running) return;
    setRunning(true);
    rememberMonthlyRun(runId);
    setRunning(true);
    setExecutionState("running", "从检查点恢复");
    setConnection("running", "正在恢复月报任务");
    appendLog(`resume: ${runId} / 从最近检查点继续`);
    try {
      const job = await requestJson(`${backgroundJobApi(runId)}/resume`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ run_id: runId })
      });
      state.lastJobEventSeq = 0;
      (Array.isArray(job.events) ? job.events : []).forEach(applyMonthlyJobEvent);
      const data = await pollMonthlyJob(runId);
      await handleAnalysisResult(data, context);
    } catch (error) {
      handleAnalysisError(error, context);
    } finally {
      setRunning(false);
    }
  }

  async function cancelMonthlyJob() {
    if (!state.activeRunId) return;
    const button = $("cancelRunBtn");
    button.disabled = true;
    appendLog(`cancel: 已向 ${state.activeRunId} 提交取消请求`);
    try {
      await requestJson(`${backgroundJobApi(state.activeRunId)}/cancel`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ run_id: state.activeRunId })
      });
      showToast("取消请求已提交，将在当前读取步骤安全停止");
    } catch (error) {
      button.disabled = false;
      showToast(`取消失败：${error.message}`);
    }
  }

  async function handleAnalysisResult(data, context) {
    const { question, modelProvider, modelLabel, selected, mcpPlugins, analysisType, monthlyEnabled } = context;
    const passengerSkill = data.skill && data.skill.analysis_type === "passenger_car_monthly_report" ? data.skill : null;
    if (monthlyEnabled && passengerSkill && passengerSkill.output_gate !== "通过") {
      const error = new Error("月报门禁未通过，已保存诊断，未生成正式报告。");
      error.runId = data.run_id || state.activeRunId;
      error.recoverable = true;
      error.jobStatus = "input_required";
      error.code = (passengerSkill.source_package || {}).code || "monthly_data_gate_blocked";
      error.result = data;
      renderPassengerRunSummary(data);
      handleAnalysisError(error, context);
      return;
    }
    stopNarrative();
    updateStep("tools", "done", monthlyEnabled ? "月报数据、模型与所选能力准备完成。" : "模型与已勾选能力准备完成。");
    updateStep("reasoning", "done", monthlyEnabled ? "已完成月报数据包、月份与兼容模板基线核验。" : "已按当前问题完成通用市场分析。");
    updateStep("quality", "running", monthlyEnabled ? "正在汇总专用数据质量门禁结果。" : "正在执行通用报告质量检查。");
    updateStep("report", "done", monthlyEnabled ? "PPT 生成准备结果已返回。" : "市场分析报告已返回。");
    setProgress(88);

    const toolEvents = Array.isArray(data.tool_events) ? data.tool_events : [];
    if (toolEvents.length) toolEvents.forEach((item) => appendLog(`tool-call: ${item.name} / ${item.status} / ${item.detail || ""}`));
    else appendLog("audit: 本轮没有返回额外工具事件，请核对数据快照与映射验数记录");

    state.lastReport = data.answer || "";
    const skillRun = data.skill_run && data.skill_run.state ? data.skill_run : null;
    const runtimeValidation = skillRun && skillRun.state.validation ? skillRun.state.validation : null;
    const runtimePassed = !skillRun || (runtimeValidation && runtimeValidation.status === "passed");
    const draftDelivery = macroDraftDelivery(data, analysisType);
    const retainedDelivery = macroRetainedDelivery(data, analysisType);
    state.lastMeta = {
      question, modelProvider, modelLabel, selected, mcpPlugins, analysisType,
      runId: data.run_id || (skillRun && skillRun.run_id) || null,
      skillRun,
      skillDeliveryUrl: skillRun && skillRun.delivery_url ? skillRun.delivery_url : "",
      formalDeliveryAllowed: data.formal_delivery_allowed,
      deliveryMode: retainedDelivery.isRetained ? "historical_retained" : draftDelivery.isDraft ? "public_draft" : "formal",
      retainedDeliveryReady: retainedDelivery.ready, retainedDeliveryUrl: retainedDelivery.url,
      draftDeliveryReady: draftDelivery.ready,
      draftDeliveryUrl: draftDelivery.url,
      createdAt: new Date().toISOString()
    };
    $("reportArea").innerHTML = markdownToHtml(state.lastReport);
    $("lengthMetric").textContent = state.lastReport.length.toLocaleString("zh-CN");
    $("toolMetric").textContent = String(toolEvents.length || 6);

    const monthlySkill = data.skill && data.skill.analysis_type === "passenger_car_monthly_report" ? data.skill : null;
    const monthlyPackage = monthlySkill && monthlySkill.source_package ? monthlySkill.source_package : null;
    const serverQuality = data.quality && data.quality.overall_status ? data.quality : null;
    const quality = draftDelivery.isDraft ? {
      title: "公开数据草稿验收",
      overall_status: draftDelivery.ready ? "草稿验收通过" : "阻断",
      impact: "仅供查阅的公开数据草稿，缺项已标注，不属于完整正式报告。",
      summary: draftDelivery.ready ? "草稿结构、数据来源与缺项标注已验收，可下载本轮PPTX。" : "草稿交付契约或独立验收未通过，下载已阻断。",
      formal_delivery_allowed: false,
      checks: [
        { name: "草稿独立验收", status: draftDelivery.ready ? "通过" : "阻断", evidence: draftDelivery.ready ? `运行编号：${draftDelivery.runId}，下载本轮已验收文件。` : "缺少可核对的验收状态、运行编号或专用下载地址。" },
        { name: "报告范围", status: "警告", evidence: "缺项标注暂无可核验数据；不使用旧模板数值或无依据预测补齐。" }
      ]
    } : serverQuality || (skillRun ? {
      overall_status: runtimePassed ? "通过" : "阻断",
      score: runtimePassed ? 100 : 0,
      summary: runtimePassed
        ? "完整 Skill 包的任务图、交付物和运行时验收均已通过。"
        : "Skill 运行时验收未通过；系统不会把文字回答或未验证文件标记为完成。",
      checks: (runtimeValidation && Array.isArray(runtimeValidation.checks) ? runtimeValidation.checks : []).map((item) => ({
        name: item.id,
        status: item.passed ? "通过" : "阻断",
        evidence: item.detail || "-"
      }))
    } : monthlySkill ? {
      overall_status: monthlySkill.output_gate === "通过" ? "通过" : "阻断",
      score: monthlySkill.output_gate === "通过" ? 100 : 0,
      summary: monthlySkill.output_gate === "通过"
        ? "45 张映射卡片、报告月份和兼容模板基线均已通过，可生成 PPT。"
        : "月报专用门禁未通过，暂不可生成 PPT。",
      checks: [
        {
          name: "映射卡片完整性",
          status: monthlySkill.output_gate === "通过" ? "通过" : "阻断",
          evidence: monthlyPackage ? `可用 ${monthlyPackage.cards_usable}/${monthlyPackage.cards_expected} 张卡片。` : "未返回数据包。"
        },
        {
          name: "报告月份识别",
          status: monthlyPackage && monthlyPackage.report_month ? "通过" : "阻断",
          evidence: monthlyPackage && monthlyPackage.report_month ? `当前报告月份：${monthlyPackage.report_month}` : "未识别报告月份。"
        },
        {
          name: "旧数据隔离",
          status: monthlySkill.legacy_excel_disabled ? "通过" : "风险",
          evidence: monthlySkill.legacy_excel_disabled ? "旧版 Excel 月报技能已禁用。" : "未确认旧数据隔离状态。"
        }
      ]
    } : await evaluateQuality(state.lastReport, question, toolEvents));
    state.lastQuality = quality;
    renderQuality(quality);
    if (data.project && data.project.id) {
      fetch("/api/projects/update", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ id: data.project.id, quality })
      }).catch(() => {});
    }
    const skillGate = data.skill && data.skill.active ? data.skill.output_gate : "";
    const effective = skillRun
      ? quality.overall_status
      : skillGate && skillGate !== "通过" ? skillGate : quality.overall_status;
    updateStep("quality", "done", `综合门禁：${effective || "已完成"}。`);
    setProgress(100);
    setExecutionState(draftDelivery.isDraft && !draftDelivery.ready ? "error" : "done", draftDelivery.isDraft ? draftDelivery.ready ? "公开数据草稿就绪" : "草稿验收未通过" : data.business_status === "incomplete" ? "基准稿已生成，业务待补充" : "分析完成");
    setConnection(effective === "风险" || effective === "阻断" ? "error" : "", draftDelivery.isDraft ? draftDelivery.ready ? "公开数据草稿 · 可下载" : "公开数据草稿 · 下载阻断" : `质量门禁：${effective || "完成"}`);
    appendLog(`complete: report returned / model=${data.model_provider || modelProvider}`);
    if (skillRun) {
      appendLog(`skill-runtime: run_id=${skillRun.run_id}; status=${skillRun.state.status}; validation=${runtimeValidation ? runtimeValidation.status : "pending"}`);
      (skillRun.state.artifacts || []).forEach((item) => appendLog(`artifact: ${item.kind} / ${item.path} / ${item.bytes || 0} bytes`));
    }
    if (data.project) appendLog(`archive: 已保存到项目 / ${data.project.title || data.project.id}`);
    enableResultActions(true);
    $("pptBtn").textContent = draftDelivery.isDraft ? "下载草稿PPT" : "生成PPT版";
    if (draftDelivery.isDraft) {
      $("pptBtn").disabled = !draftDelivery.ready;
      updateStep("reasoning", "done", "已使用可核验的公开数据更新草稿，缺项单独标注。");
      updateStep("quality", "done", draftDelivery.ready ? "草稿独立验收通过；正式完整性要求未宣称通过。" : "草稿独立验收未通过，下载阻断。");
      updateStep("report", draftDelivery.ready ? "done" : "waiting", draftDelivery.ready ? "本轮公开数据草稿已就绪，可直接下载PPTX。" : "尚未发布可下载草稿。");
      $("reportArea").insertAdjacentHTML("afterbegin", `<div class="report-delivery report-delivery--draft"><strong>${draftDelivery.ready ? "公开数据草稿已就绪" : "公开数据草稿尚未通过验收"}</strong><p>缺项标注“暂无可核验数据”，不属于完整正式报告。${draftDelivery.ready ? "请点击“下载草稿PPT”获取同一运行编号的已验收文件。" : "下载已阻断，请查看执行日志。"}</p></div>`);
    } else if ((skillRun && !runtimePassed) || data.formal_delivery_allowed === false || quality.formal_delivery_allowed === false) $("pptBtn").disabled = true;
    if (retainedDelivery.isRetained) {
      $("pptBtn").disabled = !retainedDelivery.ready;
      $("pptBtn").textContent = "下载PPT";
      setExecutionState(retainedDelivery.ready ? "done" : "error", data.report_completion === "partial_completed" ? "部分完成" : retainedDelivery.ready ? "完成" : "待修复");
      $("reportArea").insertAdjacentHTML("afterbegin", `<div class="report-delivery"><strong>${data.report_completion === "partial_completed" ? "部分完成" : "完成"}</strong><p>未更新页保留模板数据，标注“暂无可核验数据”；继续任务只补采这些页。</p></div>`);
    }
    if (data.report_completion === "partial_completed" && retainedDelivery.ready) {
      const resumeButton=document.createElement("button");resumeButton.className="secondary-btn";resumeButton.textContent="继续补采未更新页";
      resumeButton.addEventListener("click", () => resumeMonthlyJob(retainedDelivery.runId, {question,modelProvider,modelLabel,selected,mcpPlugins,analysisType}));
      $("reportArea").prepend(resumeButton);
      $("qualityMetric").textContent="部分完成";
      renderQuality({...quality,overall_status:"部分完成",summary:`${(data.pending_pages || []).length}页暂无可核验数据，保留模板历史；其余页面已更新。`});
      setConnection("", "部分完成 · 可下载");
      updateStep("intent","done","报告月份与历史增量更新范围已确定。");
      updateStep("tools","done","原始来源凭据与已成功数据已保存，可继续复用。");
      updateStep("reasoning","done","根据已核验事实更新主题句、图表和汇总表。");
      updateStep("quality","done","数据、缺项标注、结构和33页Office版面验收通过。");
      updateStep("report","waiting",`${(data.pending_pages || []).length}页待补采；已生成可下载PPT。`);
    }
    showToast(draftDelivery.isDraft ? draftDelivery.ready ? "公开数据草稿已验收，可直接下载" : "草稿验收未通过，下载已阻断" : data.business_status === "incomplete" ? "基准稿已归档，业务验收仍待补齐" : data.project ? "分析报告已生成并归档到项目" : "分析报告已生成");
  }

  function handleAnalysisError(error, context) {
    stopNarrative();
    enableResultActions(false);
    state.lastMeta = null;
    const runId = error.runId || state.activeRunId;
    if (error.code === "data_source_login_required") {
      updateStep("tools", "running", "月报专用浏览器已打开，等待完成登录后从检查点恢复。此过程不会操作日常浏览器。");
      updateStep("reasoning", "waiting", "完成登录前不会进入报告生成。");
      setProgress(32);
      setExecutionState("running", "等待登录");
      setConnection("running", "等待数据源登录");
      appendLog(`WAITING: ${error.message}`);
      emptyReport("请先完成数据源登录", error.message, "登录后从检查点恢复");
    } else if (error.code === "data_source_page_not_ready") {
      updateStep("tools", "running", "数据源页面已打开，等待卡片完成加载后从检查点恢复。");
      updateStep("reasoning", "waiting", "卡片加载完成前不会进入报告生成。");
      setProgress(36);
      setExecutionState("running", "等待数据加载");
      setConnection("running", "等待卡片加载");
      appendLog(`WAITING: ${error.message}`);
      emptyReport("数据源正在加载", error.message, "从检查点恢复");
    } else if (error.code === "monthly_job_cancelled") {
      setExecutionState("error", "任务已取消");
      setConnection("", "月报任务已取消");
      appendLog(`CANCELLED: ${error.message}`);
      emptyReport("任务已取消", "已保留已完成阶段的检查点，可继续执行。", "从检查点恢复");
    } else {
      updateStep("reasoning", "running", "后台执行中断，可从最近检查点继续。" );
      setExecutionState("error", "执行中断");
      setConnection("error", "后台任务中断");
      appendLog(`ERROR: ${error.message}`);
      emptyReport("月报任务未完成", `${error.message}${runId ? `（运行编号：${runId}）` : ""}`, error.recoverable && runId ? "从检查点恢复" : "重新分析");
    }
    if (error.result && error.result.answer) {
      state.lastReport = error.result.answer;
      $("reportArea").insertAdjacentHTML("beforeend", `<div class="blocked-run-detail">${markdownToHtml(error.result.answer)}</div>`);
      if (error.result.quality) renderQuality(error.result.quality);
      $("pptBtn").disabled = true;
    }
    if (context.monthlyEnabled) {
      const result = error.result || {};
      const source = result.skill && result.skill.source_package || {};
      updateStep("report", "waiting", "未生成主旨句或PPT，已保留任务与检查点。");
      updateStep("reasoning", "waiting", "前置条件或数据校验未通过，业务分析尚未执行。");
      const blocked = Boolean(source.code) || ["report_month_conflict", "report_month_unconfirmed"].includes(error.code);
      updateStep("quality", blocked ? "blocked" : "waiting", blocked ? "请核对目标月份及具体未通过原因。" : "前置条件未满足。");
      if (blocked) { setExecutionState("error", "月报已暂停"); setConnection("error", "月份或数据门禁阻断"); }
      $("pptBtn").disabled = true;
      if (result.answer) {
        $("copyBtn").disabled = false; $("downloadBtn").disabled = false;
        $("lengthMetric").textContent = result.answer.length.toLocaleString("zh-CN");
        const quality = result.quality || {overall_status: "阻断", score: 0, summary: "数据门禁未通过，已保存诊断。", checks: [
          {name: "卡片完整性", status: "阻断", evidence: `已识别 ${source.cards_captured || 0}/${source.cards_expected || 45} 张；可用 ${source.cards_usable || 0}/${source.cards_expected || 45} 张。`},
          {name: "目标月份", status: source.report_month ? "通过" : "阻断", evidence: source.report_month || "未确认"}]};
        state.lastQuality = quality; renderQuality(quality);
      }
    }
    const retry = $("dynamicEmptyButton");
    if (retry) {
      if (runId && error.recoverable !== false) retry.addEventListener("click", () => resumeMonthlyJob(runId, context));
      else retry.addEventListener("click", runAnalysis);
    }
    showToast(error.jobStatus === "cancelled" ? "月报任务已取消" : "月报任务暂停，请查看执行日志");
  }

  async function runAnalysis() {
    if (state.running) return;
    if ($("questionInput").readOnly) { showToast("当前是历史任务，请先重置后开始新分析"); return; }
    let question = $("questionInput").value.trim();
    if (!question) { showToast("请先输入分析任务"); $("questionInput").focus(); return; }
    const modelProvider = $("modelSelect").value;
    const modelLabel = $("modelSelect").selectedOptions[0].textContent;
    const selected = selectedCapabilities();
    const mcpPlugins = selectedMcpPlugins(selected);
    const monthlyEnabled = selected.includes("passenger_car_monthly_report");
    const macroEnabled = selected.includes("macro_monthly_report");
    const analysisType = macroEnabled ? "macro_monthly_report" : monthlyEnabled ? "passenger_car_monthly_report" : "";
    const draftFields = macroEnabled ? { delivery_mode: "historical_retained", history_retention_confirmed: true } : {};

    if (macroEnabled) {
      if (!$("macroReportMonth").value) {
        showToast("请先选择宏观经济月报的报告月份");
        $("macroReportMonth").focus();
        return;
      }
      const monthContext = `报告月份：${macroReportMonthLabel()}。逐页数据台账由智能体在执行过程中自动建立，不要求业务人员上传台账。`;
      if (!question.includes("报告月份：")) question += `\n\n${monthContext}`;
      if (draftFields.delivery_mode === "public_draft") question += "\n\n交付方式：公开数据草稿。缺项标注暂无可核验数据，不属于完整正式报告；仅发布通过草稿独立验收的本轮PPTX。";
    }

    toggleCapabilities(false);
    setRunning(true);
    enableResultActions(false);
    state.lastReport = "";
    state.lastQuality = null;
    state.lastMeta = null;
    addUserMessage(question);
    initSteps();
    setProgress(8);
    setExecutionState("running", "执行中");
    setConnection("running", `${modelLabel} 分析中`);
    $("eventLog").textContent = "开始接收智能体执行日志...";
    const taskLabel = macroEnabled ? "宏观经济月报" : monthlyEnabled ? "乘用车月报智能生成" : "通用市场分析";
    appendLog(`task: ${taskLabel} / model=${modelLabel}`);
    appendLog(`capability: 已选择 ${selected.length} 项技能与插件`);
    appendLog(`binding: 技能=${selected.filter((id) => !mcpPluginByCapability[id]).join(",") || "无"}；插件=${mcpPlugins.join(",") || "无"}`);
    if (macroEnabled) appendLog("执行规则：缺项保留模板并标注暂无可核验数据；仅补采未更新页。");
    updateStep("intent", "done", macroEnabled ? `已识别为${macroReportMonthLabel()}宏观经济月报更新任务。` : monthlyEnabled ? "已识别为中国乘用车月度市场分析任务。" : "已识别为通用汽车市场分析任务。");
    updateStep("tools", "running", macroEnabled ? "正在读取固定模板、建立内部逐页核对台账并准备权威数据检索。" : monthlyEnabled ? "正在检查数据源登录态并读取页面快照。" : "正在准备已勾选的技能、插件与分析上下文。");
    emptyReport("智能体正在分析", macroEnabled ? "智能体将自动建立数据台账并完成数据检索、口径校验与报告生成。" : monthlyEnabled ? "报告将在完成数据门禁与业务推理后显示，请观察左侧执行过程。" : "系统将只调用当前勾选的能力执行分析。", "");
    if (!monthlyEnabled && !macroEnabled) startNarrative(modelLabel, false);

    try {
      let data;
      if (monthlyEnabled || macroEnabled) {
        data = await startMonthlyBackgroundJob({
          agent: "market_strategy",
          question,
          analysis_type: analysisType,
          model_provider: modelProvider,
          capabilities: selected,
          mcp_plugins: mcpPlugins,
          report_month: macroEnabled ? $("macroReportMonth").value : monthlyEnabled ? $("passengerReportMonth").value || undefined : undefined,
          mode: "historical_update",
          ...draftFields
        });
      } else {
        appendLog("route: 未选择月报技能，跳过月报专用链路");
        data = await requestJson("/api/chat", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            agent: "market_strategy",
            question,
            analysis_type: analysisType,
            model_provider: modelProvider,
            capabilities: selected,
            mcp_plugins: mcpPlugins
          })
        });
      }
      await handleAnalysisResult(data, { question, modelProvider, modelLabel, selected, mcpPlugins, analysisType, monthlyEnabled });
    } catch (error) {
      if (monthlyEnabled || macroEnabled) {
        handleAnalysisError(error, { question, modelProvider, modelLabel, selected, mcpPlugins, analysisType, monthlyEnabled });
      } else {
        stopNarrative();
        updateStep("tools", "done", "请求已发送。");
        updateStep("reasoning", "running", "执行中断，请根据错误信息调整后重试。");
        setProgress(68);
        setExecutionState("error", "执行失败");
        setConnection("error", "分析失败");
        appendLog(`ERROR: ${error.message}`);
        emptyReport("分析失败", error.message, "重新分析");
        const retry = $("dynamicEmptyButton");
        if (retry) retry.addEventListener("click", runAnalysis);
        showToast("分析失败，请查看执行日志");
      }
    } finally {
      setRunning(false);
    }
  }

  function buildDownloadMarkdown() {
    if (!state.lastReport) return "";
    const meta = state.lastMeta || {};
    return [
      "# 乘用车市场战略决策分析报告",
      "",
      `- 生成时间：${new Date().toLocaleString("zh-CN")}`,
      `- 执行智能体：市场战略Agent`,
      `- 大模型：${meta.modelLabel || "-"}`,
      `- 分析任务：${meta.question || "-"}`,
      "",
      state.lastReport
    ].join("\n");
  }

  function downloadText(filename, text) {
    const blob = new Blob([text], { type: "text/markdown;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = filename;
    document.body.appendChild(link);
    link.click();
    link.remove();
    URL.revokeObjectURL(url);
  }

  async function copyText(text, successMessage) {
    if (!text) return;
    try {
      await navigator.clipboard.writeText(text);
    } catch (_) {
      const area = document.createElement("textarea");
      area.value = text;
      area.style.position = "fixed";
      area.style.opacity = "0";
      document.body.appendChild(area);
      area.select();
      document.execCommand("copy");
      area.remove();
    }
    showToast(successMessage);
  }

  async function generatePpt() {
    if (!state.lastReport) return;
    if (state.lastMeta && state.lastMeta.deliveryMode === "historical_retained") {
      if (!state.lastMeta.retainedDeliveryReady || !state.lastMeta.retainedDeliveryUrl) return showToast("历史延续版验收未通过");
      const link = document.createElement("a");link.href=macroApiUrl(state.lastMeta.retainedDeliveryUrl);link.download="";
      document.body.appendChild(link);link.click();link.remove();return;
    }
    if (state.lastMeta && state.lastMeta.deliveryMode === "public_draft") {
      if (!state.lastMeta.draftDeliveryReady || !state.lastMeta.draftDeliveryUrl) {
        $("pptBtn").disabled = true;
        showToast("草稿验收未通过或下载地址缺失，下载已阻断");
        return;
      }
      const link = document.createElement("a");
      link.href = macroApiUrl(state.lastMeta.draftDeliveryUrl);
      link.download = "";
      document.body.appendChild(link);
      link.click();
      link.remove();
      appendLog(`ppt-draft: download validated public draft / run_id=${state.lastMeta.runId}`);
      showToast("正在下载本轮已验收的公开数据草稿PPTX");
      return;
    }
    if ((state.lastQuality && state.lastQuality.formal_delivery_allowed === false) || (state.lastMeta && state.lastMeta.formalDeliveryAllowed === false)) {
      showToast("业务验收未通过，正式PPT导出已阻断");
      return;
    }
    if (state.lastMeta && state.lastMeta.analysisType === "macro_monthly_report" && state.lastMeta.archivedMacro === true && !state.lastMeta.macroDeliveryReady) {
      $("pptBtn").disabled = true;
      showToast("原宏观任务的产物与验收未能核验，下载已阻断；不会重新生成PPT");
      return;
    }
    const skillDeliveryUrl = state.lastMeta && state.lastMeta.skillDeliveryUrl ? state.lastMeta.skillDeliveryUrl : "";
    if (skillDeliveryUrl) {
      const link = document.createElement("a");
      link.href = skillDeliveryUrl;
      link.download = "";
      document.body.appendChild(link);
      link.click();
      link.remove();
      appendLog(`ppt: download verified Skill artifact ${skillDeliveryUrl}`);
      showToast("正在下载 Skill 生成并验收的 PPTX");
      return;
    }
    const analysisType = state.lastMeta && state.lastMeta.analysisType ? state.lastMeta.analysisType : "";
    const selected = state.lastMeta && Array.isArray(state.lastMeta.selected) ? state.lastMeta.selected : [];
    const monthlyEnabled = analysisType === "passenger_car_monthly_report" && selected.includes("passenger_car_monthly_report");
    const runId = state.lastMeta && state.lastMeta.runId ? state.lastMeta.runId : "";
    if (monthlyEnabled && !runId) {
      showToast("缺少本轮月报运行编号，请重新执行月报分析");
      return;
    }
    const status = state.lastQuality && state.lastQuality.overall_status;
    if (["风险", "阻断"].includes(status) && !window.confirm(`质量门禁状态为“${status}”，仍要生成 PPT 草稿吗？`)) return;
    const button = $("pptBtn");
    button.disabled = true;
    button.textContent = "生成中";
    appendLog("ppt: 正在生成可编辑汇报版");
    try {
      const response = await fetch("/api/ppt", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          markdown: state.lastReport,
          title: monthlyEnabled ? "乘用车市场月度分析报告" : "市场战略分析报告",
          analysis_type: analysisType,
          capabilities: selected,
          run_id: runId
        })
      });
      const data = await response.json();
      if (!response.ok || data.error || data.success === false) throw new Error(data.error || `PPT 服务返回 HTTP ${response.status}`);
      const url = data.pptx_url || data.html_url;
      const label = data.pptx_url ? "下载可编辑 PPTX" : "打开 HTML PPT";
      const pptLinkAttribute = data.pptx_url ? "download" : 'target="_blank" rel="noopener"';
      $("reportArea").insertAdjacentHTML("afterbegin", `
        <div class="report-delivery"><strong>PPT 版已生成</strong><p>报告正文仍保留在下方，可继续复制或下载 Markdown。</p><a href="${escapeHtml(url)}" ${pptLinkAttribute}>${label}</a></div>`);
      appendLog(`ppt: generated ${url}`);
      if (data.cards_usable) appendLog(`ppt-source: ${data.report_month} / ${data.cards_usable}/${data.cards_expected} 张卡片`);
      showToast("PPT 版已生成");
    } catch (error) {
      appendLog(`ppt-error: ${error.message}`);
      showToast(`PPT 生成失败：${error.message}`);
    } finally {
      button.disabled = false;
      button.textContent = "生成PPT版";
    }
  }

  function resetPage() {
    if (state.running) { showToast("任务正在执行，请先取消任务后再重置"); return; }
    stopNarrative();
    const previousRunId = state.lastMeta && state.lastMeta.runId;
    [ACTIVE_MACRO_RUN_KEY, ACTIVE_MONTHLY_RUN_KEY].forEach(key => {
      if (previousRunId && window.localStorage.getItem(key) === previousRunId) window.localStorage.removeItem(key);
    });
    const params = new URLSearchParams(window.location.search);
    params.delete("project");
    params.delete("demo");
    params.delete("run");
    params.set("new", "1");
    window.history.replaceState(null, "", `${window.location.pathname}?${params.toString()}${window.location.hash || ""}`);
    state.activeRunId = null;
    state.lastJobEventSeq = 0;
    $("questionInput").readOnly = false;
    setRunning(false);
    state.lastReport = "";
    state.lastMeta = null;
    state.lastQuality = null;
    window.localStorage.removeItem(LAST_MACRO_DRAFT_KEY);
    $("pptBtn").textContent = "生成PPT版";
    syncTaskPreset(true);
    const message = $("conversationStream").querySelector(".user-message");
    if (message) message.remove();
    $("qualityMetric").textContent = "-";
    $("qualityMetric").style.color = "";
    $("lengthMetric").textContent = "-";
    $("toolMetric").textContent = "6";
    initSteps();
    setProgress(0);
    setExecutionState("", "等待执行");
    renderInitialQuality();
    emptyReport("还没有分析结果", "选择模型、技能与插件并点击“开始分析”后，这里会展示完整报告。", "开始第一次分析");
    $("dynamicEmptyButton").addEventListener("click", runAnalysis);
    enableResultActions(false);
    setConnection("", "后端已连接");
    showToast("已清空本轮状态");
  }

  async function refreshConfig() {
    try {
      const response = await fetch("/api/config", { cache: "no-store" });
      const data = await response.json();
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      const requestedProvider = new URLSearchParams(window.location.search).get("model_provider");
      const selectedProvider = requestedProvider || data.active_provider;
      if (["deepseek_flash", "deepseek_pro"].includes(selectedProvider)) $("modelSelect").value = selectedProvider;
      setConnection("", "后端已连接");
    } catch (_) {
      setConnection("error", "后端未连接");
    }
  }

  async function restoreActiveMonthlyJob() {
    const params = new URLSearchParams(window.location.search);
    if (params.get("new") === "1" || params.get("project") || params.get("demo")) return;
    const pageRunId = params.get("run");
    // Explicit skill/agent launches are new tasks, never global-cache replays.
    if (!pageRunId && ["skills", "plugins", "agent"].some(key => params.has(key))) return;
    const runId = pageRunId || window.localStorage.getItem(ACTIVE_MACRO_RUN_KEY) || window.localStorage.getItem(ACTIVE_MONTHLY_RUN_KEY);
    if (!runId) return;
    const macroEnabled = runId.startsWith("macro-");
    try {
      const job = await fetchMonthlyJobSnapshot(runId);
      if (!pageRunId && !["queued", "running"].includes(job.status)) {
        // Compatibility for old active-run bookmarks: completed/failed jobs
        // belong in Projects, not an otherwise fresh analysis page.
        [ACTIVE_MACRO_RUN_KEY, ACTIVE_MONTHLY_RUN_KEY].forEach(key => {
          if (window.localStorage.getItem(key) === runId) window.localStorage.removeItem(key);
        });
        return;
      }
      const payload = job.payload || {};
      const selected = Array.isArray(payload.capabilities) ? payload.capabilities : [macroEnabled ? "macro_monthly_report" : "passenger_car_monthly_report"];
      const mcpPlugins = Array.isArray(payload.mcp_plugins) ? payload.mcp_plugins : [];
      const modelProvider = payload.model_provider || "deepseek_flash";
      if (["deepseek_flash", "deepseek_pro"].includes(modelProvider)) $("modelSelect").value = modelProvider;
      const modelLabel = $("modelSelect").selectedOptions[0].textContent;
      const question = payload.question === LEGACY_MONTHLY_QUESTION
        ? DEFAULT_QUESTION
        : payload.question || (macroEnabled ? macroQuestion() : DEFAULT_QUESTION);
      const context = {
        question,
        modelProvider,
        modelLabel,
        selected,
        mcpPlugins,
        analysisType: macroEnabled ? "macro_monthly_report" : "passenger_car_monthly_report",
        monthlyEnabled: !macroEnabled
      };
      $("capabilityList").querySelectorAll("input").forEach((input) => { input.checked = selected.includes(input.value); });
      updateCapabilitySummary();
      if (macroEnabled && payload.report_month) $("macroReportMonth").value = payload.report_month;
      if (!macroEnabled) { $("passengerReportMonth").value = payload.report_month || ""; renderPassengerRunSummary(job); }
      syncMacroRunConfig();
      $("questionInput").value = question;
      addUserMessage(question);
      initSteps();
      $("eventLog").textContent = "正在恢复月报后台任务...";
      rememberMonthlyRun(runId);
      setRunning(true);
      setExecutionState("running", "后台任务恢复中");
      appendLog(`run-id: ${runId} / 页面刷新后继续接收真实进度`);
      state.lastJobEventSeq = 0;
      (Array.isArray(job.events) ? job.events : []).forEach(applyMonthlyJobEvent);
      const data = await pollMonthlyJob(runId);
      await handleAnalysisResult(data, context);
    } catch (error) {
      const modelProvider = $("modelSelect").value;
      const selected = selectedCapabilities();
      handleAnalysisError(error, {
        question: $("questionInput").value.trim() || DEFAULT_QUESTION,
        modelProvider,
        modelLabel: $("modelSelect").selectedOptions[0].textContent,
        selected,
        mcpPlugins: selectedMcpPlugins(selected),
        analysisType: macroEnabled ? "macro_monthly_report" : "passenger_car_monthly_report",
        monthlyEnabled: !macroEnabled
      });
    } finally {
      setRunning(false);
    }
  }

  async function loadArchivedProject() {
    const params = new URLSearchParams(window.location.search);
    if (params.get("new") === "1") return;
    const projectId = params.get("project");
    const demoId = params.get("demo");
    if (!projectId && !demoId) return;
    try {
      setConnection("running", "正在加载归档项目");
      let data;
      if (projectId) {
        const response = await fetch(`/api/projects?id=${encodeURIComponent(projectId)}`, { cache: "no-store" });
        data = await response.json();
        if (!response.ok || data.error) throw new Error(data.error || `项目服务返回 HTTP ${response.status}`);
      } else {
        data = JSON.parse(localStorage.getItem("strategy-demo-project") || "null");
        if (!data || data.id !== demoId) throw new Error("演示任务回放数据已过期。");
      }

      const modelProvider = ["deepseek_flash", "deepseek_pro"].includes(data.model_provider) ? data.model_provider : "deepseek_flash";
      $("modelSelect").value = modelProvider;
      const archivedSkillRun = data.skill_run || {};
      const archivedMode = data.delivery_mode || archivedSkillRun.delivery_mode || (archivedSkillRun.state && archivedSkillRun.state.delivery_mode);
      if (data.analysis_type === "macro_monthly_report") {
        const runId = data.run_id || archivedSkillRun.run_id;
        let job = {};
        let blockedReason = "";
        if (/^macro-\d{8}-\d{6}-[a-f0-9]{8}$/.test(runId || "")) {
          try { job = await requestJson(`${backgroundJobApi(runId)}/${encodeURIComponent(runId)}`, { cache: "no-store" }, true); }
          catch (error) { blockedReason = `原运行记录暂时无法核验：${error.message}`; }
        } else blockedReason = "归档项目缺少有效的宏观运行编号，不能确认原产物。";
        const isDraft = archivedMode === "public_draft";
        const isRetained = archivedMode === "historical_retained";
        const result = { ...(job.result || {}), answer: (job.result && job.result.answer) || data.answer || "",
          delivery_mode: isRetained ? "historical_retained" : isDraft ? "public_draft" : "formal", run_id: runId, job_status: job.status };
        const delivery = isRetained ? macroRetainedDelivery(result, "macro_monthly_report") : isDraft ? macroDraftDelivery(result, "macro_monthly_report") : macroFormalDelivery(result);
        if (!delivery.ready) {
          blockedReason ||= "原任务尚未通过对应交付验收，或原产物地址与运行编号不一致。";
          result.formal_delivery_allowed = false;
          result.quality = { overall_status: "阻断", score: null, formal_delivery_allowed: false,
            summary: blockedReason, checks: [{ name: "原任务产物核验", status: "阻断", evidence: blockedReason }] };
        }
        const selected = Array.isArray(data.capabilities) ? data.capabilities : ["macro_monthly_report"];
        $("capabilityList").querySelectorAll("input").forEach((input) => { input.checked = selected.includes(input.value); });
        updateCapabilitySummary();
        if (job.payload && job.payload.report_month) $("macroReportMonth").value = job.payload.report_month;
        $("questionInput").value = data.question || macroQuestion();
        initSteps();
        $("eventLog").textContent = `回放宏观历史任务：${runId || "缺少运行编号"}`;
        await handleAnalysisResult(result, {
          question: $("questionInput").value, modelProvider,
          modelLabel: $("modelSelect").selectedOptions[0].textContent,
          selected, mcpPlugins: selectedMcpPlugins(selected), analysisType: "macro_monthly_report", monthlyEnabled: false
        });
        state.lastMeta.archivedMacro = true;
        state.lastMeta.macroDeliveryReady = delivery.ready;
        state.lastMeta.skillDeliveryUrl = isDraft ? state.lastMeta.skillDeliveryUrl : delivery.url;
        state.lastMeta.formalDeliveryAllowed = !isDraft && delivery.ready;
        $("pptBtn").disabled = !delivery.ready;
        if (!isDraft) $("pptBtn").textContent = "下载已验收PPT";
        if (blockedReason) {
          $("reportArea").insertAdjacentHTML("afterbegin", `<div class="blocked-run-detail"><strong>原宏观PPT下载已阻断</strong><p>${escapeHtml(blockedReason)} 保留历史文本供查阅；不会改走通用PPT重新生成。</p></div>`);
          updateStep("report", "waiting", "原产物未能核验，下载已阻断；不会重新生成PPT。");
          setConnection("error", "历史任务 · 原产物核验未通过");
        }
        $("questionInput").readOnly = true;
        $("macroReportMonth").disabled = true;
        $("runBtn").disabled = true;
        $("runBtn").textContent = "历史任务";
        // 当归档项目指向的运行仍在跑/排队时，沿用该 run_id 暴露取消按钮，
        // 让用户在历史任务视图里也能安全停掉背后那个 worker。
        if (runId && (job.status === "running" || job.status === "queued")) {
          state.activeRunId = runId;
          $("cancelRunBtn").hidden = false;
          $("cancelRunBtn").disabled = false;
        }
        showToast(delivery.ready ? "已回放原宏观任务及已验收产物" : "历史任务已加载，原PPT下载核验未通过");
        return;
      }
      $("questionInput").value = data.question === LEGACY_MONTHLY_QUESTION
        ? DEFAULT_QUESTION
        : data.question || DEFAULT_QUESTION;
      state.lastReport = data.answer || "";
      state.lastMeta = {
        question: data.question || "",
        modelProvider,
        modelLabel: $("modelSelect").selectedOptions[0].textContent,
        selected: [],
        runId: data.run_id || archivedSkillRun.run_id || null,
        formalDeliveryAllowed: data.formal_delivery_allowed !== false,
        createdAt: data.created_at || new Date().toISOString()
      };
      state.lastQuality = data.quality && data.quality.overall_status
        ? data.quality
        : { overall_status: data.quality_status || "已归档" };
      $("reportArea").innerHTML = markdownToHtml(state.lastReport);
      $("lengthMetric").textContent = Number(data.answer_length || state.lastReport.length).toLocaleString("zh-CN");
      $("toolMetric").textContent = String(data.tool_count || 6);
      if (data.quality && data.quality.overall_status) {
        renderQuality(data.quality);
      } else {
        $("qualityMetric").textContent = data.quality_status || "已归档";
        $("qualityMetric").style.color = "var(--green)";
        $("qualityPanel").style.flexWrap = "nowrap";
        $("qualityPanel").innerHTML = `<div><span class="quality-mark" aria-hidden="true"><svg viewBox="0 0 24 24"><path d="M12 3 4.5 6v5.3c0 4.6 3.2 8.2 7.5 9.7 4.3-1.5 7.5-5.1 7.5-9.7V6z"/><path d="m9 12 2 2 4-4"/></svg></span><div><h3>数据质量门禁</h3><p>这是已完成的历史分析结果，保留生成时的门禁状态。</p></div></div><span class="quality-status pass">${escapeHtml(data.quality_status || "已归档")}</span>`;
      }
      initSteps();
      const stages = Array.isArray(data.execution_stages) ? data.execution_stages : [];
      if (stages.length) stages.forEach((stage) => updateStep(stage.id, stage.status || "done", stage.summary || "已完成。"));
      else {
        updateStep("intent", "done", "历史任务与意图已加载。");
        updateStep("tools", "done", "生成时的工具与证据状态已归档。");
        updateStep("reasoning", "done", "业务分析框架已完成。");
        updateStep("quality", "done", `归档门禁：${data.quality_status || "已完成"}。`);
        updateStep("report", "done", "完整报告已从项目档案加载。");
      }
      const archivedCapabilities = Array.isArray(data.capabilities) ? data.capabilities : [];
      $("capabilityList").querySelectorAll("input").forEach((input) => { input.checked = archivedCapabilities.includes(input.value); });
      state.lastMeta.selected = archivedCapabilities;
      state.lastMeta.analysisType = data.analysis_type || "";
      updateCapabilitySummary();
      setProgress(100);
      setExecutionState("done", "任务回放");
      setConnection("", "历史任务回放");
      const toolEvents = Array.isArray(data.tool_events) ? data.tool_events : [];
      const skillEvents = data.skill && Array.isArray(data.skill.events) ? data.skill.events : [];
      const replayLines = [
        `回放任务：${data.title || projectId || demoId}`,
        ...(state.lastMeta.runId ? [`原运行编号：${state.lastMeta.runId}`] : []),
        `创建时间：${data.created_at || data.time_label || "-"}`,
        `执行模型：${state.lastMeta.modelLabel}`,
        `任务状态：${data.status || "已完成"}`,
        ...toolEvents.map((item) => `tool-call: ${item.name || "tool"} / ${item.status || "done"} / ${item.detail || ""}`),
        ...skillEvents.map((item) => `skill: ${item.name || item.stage || "market-analysis"} / ${item.status || "done"} / ${item.detail || ""}`),
        "完整报告已从项目档案加载。"
      ];
      $("eventLog").textContent = replayLines.join("\n");
      $("questionInput").readOnly = true;
      $("runBtn").disabled = true;
      $("runBtn").textContent = "历史任务";
      // 乘用车月报归档项目：探测背后 job 是否还活着以决定是否暴露取消按钮
      const liveMonthlyRunId = data.run_id || archivedSkillRun.run_id || null;
      if (liveMonthlyRunId && /^month-\d{8}-\d{6}-[a-f0-9]{8}$/.test(liveMonthlyRunId)) {
        try {
          const liveJob = await requestJson(`${backgroundJobApi(liveMonthlyRunId)}/${encodeURIComponent(liveMonthlyRunId)}`, { cache: "no-store" }, true);
          if (liveJob && (liveJob.status === "running" || liveJob.status === "queued")) {
            state.activeRunId = liveMonthlyRunId;
            $("cancelRunBtn").hidden = false;
            $("cancelRunBtn").disabled = false;
          }
        } catch (_) { /* 静默：拉不到 job 时不显示取消按钮即可 */ }
      }
      enableResultActions(Boolean(state.lastReport));
      if (data.formal_delivery_allowed === false || (data.quality && data.quality.formal_delivery_allowed === false)) $("pptBtn").disabled = true;
      showToast("已进入历史任务回放");
    } catch (error) {
      setConnection("error", "归档加载失败");
      showToast(`项目加载失败：${error.message}`);
    }
  }

  function bindEvents() {
    $("capabilityTrigger").addEventListener("click", () => toggleCapabilities());
    $("closeCapabilities").addEventListener("click", () => toggleCapabilities(false));
    $("selectAllCapabilities").addEventListener("click", () => {
      const inputs = Array.from($("capabilityList").querySelectorAll("input"));
      const shouldCheck = inputs.some((input) => !input.checked);
      inputs.forEach((input) => { input.checked = shouldCheck; });
      if (shouldCheck) {
        const macro = $("capabilityList").querySelector('input[value="macro_monthly_report"]');
        if (macro) enforceMonthlySkillExclusivity(macro);
      }
      updateCapabilitySummary();
    });
    document.addEventListener("click", (event) => {
      if (!event.target.closest(".capability-picker")) toggleCapabilities(false);
    });
    $("runBtn").addEventListener("click", runAnalysis);
    $("cancelRunBtn").addEventListener("click", cancelMonthlyJob);
    $("emptyStartBtn").addEventListener("click", runAnalysis);
    $("questionInput").addEventListener("keydown", (event) => {
      if (event.key === "Enter" && (event.ctrlKey || event.metaKey)) runAnalysis();
    });
    $("resetBtn").addEventListener("click", resetPage);
    $("copyLogBtn").addEventListener("click", () => copyText($("eventLog").textContent, "执行日志已复制"));
    $("copyBtn").addEventListener("click", () => copyText(state.lastReport, "报告已复制"));
    $("downloadBtn").addEventListener("click", () => {
      if (!state.lastReport) return;
      const stamp = new Date().toISOString().slice(0, 19).replace(/[:T]/g, "-");
      downloadText(`乘用车市场月报-${stamp}.md`, buildDownloadMarkdown());
      appendLog("download: markdown report exported");
      showToast("Markdown 报告已下载");
    });
    $("pptBtn").addEventListener("click", generatePpt);
    $("macroReportMonth").addEventListener("change", () => syncTaskPreset());
  }

  function initializeMacroMonth() {
    const now = new Date();
    const requestedMonth = new URLSearchParams(window.location.search).get("month");
    $("macroReportMonth").value = /^\d{4}-\d{2}$/.test(requestedMonth || "") ? requestedMonth : `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}`;
  }

  // Older running services cache the HTML at startup. Remove the obsolete
  // controls there as well, preserving their authenticated browser session.
  ["macroReportMode","macroRetained","macroPublicDraft"].forEach(id => {
    const obsolete=document.getElementById(id);if(obsolete) obsolete.closest("label").remove();
  });
  const projectReturnLink=document.querySelector(".home-link");
  if(projectReturnLink){
    projectReturnLink.href="/#projects";
    projectReturnLink.textContent="返回项目";
    projectReturnLink.setAttribute("aria-label","返回项目任务列表");
  }
  initSteps();
  initializeMacroMonth();
  renderCapabilities();
  bindEvents();
  refreshConfig();
  loadArchivedProject();
  restoreActiveMonthlyJob();
})();
