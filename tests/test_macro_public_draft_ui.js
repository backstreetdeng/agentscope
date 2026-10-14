"use strict";

// Evaluate the actual workbench functions with an offline DOM and HTTP double.
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");
const source = fs.readFileSync(path.join(__dirname, "../assets/strategy-analysis.js"), "utf8");
const boot = source.lastIndexOf("  initSteps();\n  initializeMacroMonth();");
assert.ok(boot > 0, "The initialization boundary must be located without running a real page.");
const instrumented = source.slice(0, boot) + `
  globalThis.workbench = { macroDraftRequestFields, macroDraftDelivery, macroFormalDelivery, handleAnalysisResult,
    pollMonthlyJob, restoreActiveMonthlyJob, loadArchivedProject, generatePpt, runAnalysis, resetPage, state };
})();`;
const homeSource = fs.readFileSync(path.join(__dirname, "../assets/home.js"), "utf8");
const freshLinkStart = homeSource.indexOf("  function initializeNewAnalysisLinks() {");
const freshLinkEnd = homeSource.indexOf("\n  function init() {", freshLinkStart);
assert.ok(freshLinkStart > 0 && freshLinkEnd > freshLinkStart);
const freshLinks = [{}, {}];
vm.runInNewContext(homeSource.slice(freshLinkStart, freshLinkEnd) + "\ninitializeNewAnalysisLinks();", {
  utils: { qsa(selector) {
    assert.equal(selector, 'a[aria-label="在新窗口新建一次市场分析"]');
    return freshLinks.map(link => ({ setAttribute(name, value) { link[name] = value; } }));
  } }
});
assert.ok(freshLinks.every(link => link.href === "/strategy-analysis.html?new=1"),
  "In-memory older home HTML must receive the fresh entry flag without a service restart.");
const runId = "macro-20261004-100000-1234abcd";

function draftResult() {
  return {
    answer: "# 公开数据草稿\n部分指标暂无可核验数据。", run_id: runId,
    delivery_mode: "public_draft", draft_delivery_allowed: true, formal_delivery_allowed: false,
    business_status: "draft_passed", job_status: "draft_ready",
    draft_delivery_url: `/api/macro-report/draft/${runId}`,
    skill_run: { run_id: runId, delivery_mode: "public_draft", delivery_url: `/api/macro-report/draft/${runId}`,
      state: { status: "draft_ready", delivery_mode: "public_draft", draft_validation: { status: "passed" }, artifacts: [] } }
  };
}

function formalResult() {
  return { answer: "# 原宏观正式报告", run_id: runId, delivery_mode: "formal", job_status: "completed",
    business_status: "passed", formal_delivery_allowed: true, quality: { overall_status: "通过" },
    skill_run: { run_id: runId, delivery_mode: "formal", delivery_url: `/outputs/ppt/${runId}-原已验收月报.pptx`,
      state: { status: "passed", business_status: "passed", formal_delivery_allowed: true, validation: { status: "passed" }, artifacts: [],
        artifact_validations: ["macro_business", "pptx_structure", "powerpoint_render", "macro_layout"].map(validator => ({ validator, passed: true })) } } };
}

function sandbox(selected = ["macro_monthly_report"], checked = false, result = draftResult(), search = "", analysisType = "macro_monthly_report") {
  const nodes = new Map();
  const inputs = ["macro_monthly_report", "passenger_car_monthly_report", "policy"].map(value => ({ value, checked: selected.includes(value) }));
  const requests = [], links = [], storage = new Map(), historyRoutes = [];
  function element(id = "") {
    return {
      id, hidden: false, disabled: false, checked: false, value: "", textContent: "", innerHTML: "", dataset: {}, style: {},
      scrollHeight: 0, scrollTop: 0, parentNode: { insertBefore() {} }, selectedOptions: [{ textContent: "MiniMax M3" }],
      classList: { add() {}, remove() {} }, focus() {}, remove() {}, addEventListener() {}, setAttribute() {},
      querySelector(selector) { return selector.startsWith("input") ? inputs.find(input => selector.includes(input.value)) : element(); },
      querySelectorAll(selector) { return selector === "input:checked" ? inputs.filter(input => input.checked) : inputs; },
      insertAdjacentHTML(position, value) { this.innerHTML += value; },
      click() { if (this.href) links.push(this.href); }
    };
  }
  const document = { getElementById(id) { if (!nodes.has(id)) nodes.set(id, element(id)); return nodes.get(id); },
    createElement() { return element(); }, body: { appendChild() {} } };
  document.getElementById("questionInput").value = "生成月报";
  document.getElementById("macroReportMonth").value = "2026-09";
  document.getElementById("macroPublicDraft").checked = checked;
  document.getElementById("modelSelect").value = "minimax";
  const job = { run_id: runId, status: result.delivery_mode === "public_draft" ? "draft_ready" : "completed",
    payload: { capabilities: selected, delivery_mode: result.delivery_mode || "formal", public_draft_confirmed: checked,
      report_month: "2026-09", question: "生成月报", model_provider: "minimax" }, result, events: [] };
  const context = vm.createContext({ document, Date, URLSearchParams, Set, Array, console,
    window: { location: { search, pathname: "/strategy-analysis.html", hash: "" },
      history: { replaceState(state, unused, url) {
        historyRoutes.push(url);
        context.window.location.search = url.includes("?") ? `?${url.split("?")[1].split("#")[0]}` : "";
      } }, setTimeout() { return 1; }, clearTimeout() {}, clearInterval() {},
      localStorage: { getItem(key) { return storage.get(key) || null; }, setItem(key, value) { storage.set(key, value); }, removeItem(key) { storage.delete(key); } } },
    async fetch(url, options) { requests.push({ url, options });
      return { ok: true, status: 200, async json() {
        if (url === "/api/quality-gate") return { overall_status: "通过" };
        if (url.startsWith("/api/projects?id=")) return { ...result, analysis_type: analysisType, capabilities: selected };
        if (url === "/api/ppt") return { success: true, pptx_url: "/outputs/ppt/monthly-test.pptx", run_id: result.run_id };
        return job;
      } }; }
  });
  vm.runInContext(instrumented, context);
  return { api: context.workbench, nodes, requests, links, storage, job, context, historyRoutes };
}

const macroContext = { question: "生成月报", modelProvider: "minimax", modelLabel: "MiniMax M3",
  selected: ["macro_monthly_report"], mcpPlugins: [], analysisType: "macro_monthly_report", monthlyEnabled: false };

async function main() {
  const functions = sandbox().api;
  assert.equal(JSON.stringify(functions.macroDraftRequestFields(["macro_monthly_report"], false)), "{}");
  assert.equal(JSON.stringify(functions.macroDraftRequestFields(["passenger_car_monthly_report"], true)), "{}");
  assert.equal(JSON.stringify(functions.macroDraftRequestFields(["policy"], true)), "{}");
  assert.equal(JSON.stringify(functions.macroDraftRequestFields(["macro_monthly_report"], true)),
    '{"delivery_mode":"public_draft","public_draft_confirmed":true}');
  assert.equal(functions.macroDraftDelivery(draftResult(), "macro_monthly_report").ready, true);
  assert.equal(functions.macroDraftDelivery(draftResult(), "passenger_car_monthly_report").ready, false);
  const changes = [
    r => r.draft_delivery_allowed = false,
    r => r.formal_delivery_allowed = true,
    r => r.business_status = "passed",
    r => r.skill_run.state.draft_validation.status = "failed",
    r => { r.job_status = "needs_repair"; r.skill_run.state.status = "needs_repair"; },
    r => r.job_status = "completed",
    r => r.skill_run.state.status = "completed",
    r => r.draft_delivery_url = `/api/macro-report/draft/macro-another-run`,
    r => r.draft_delivery_url = "https://example.com/report.pptx",
    r => r.skill_run.run_id = "macro-another-run",
    r => r.run_id = "../../outside"
  ];
  for (const change of changes) {
    const result = draftResult(); change(result);
    assert.equal(functions.macroDraftDelivery(result, "macro_monthly_report").ready, false);
  }
  for (const [selected, checked, expected] of [
    [["macro_monthly_report"], false, false], [["macro_monthly_report"], true, true],
    [["passenger_car_monthly_report"], true, false]
  ]) {
    const result = expected ? draftResult() : { answer: "报告", formal_delivery_allowed: true,
      quality: { overall_status: "通过" }, skill_run: { run_id: runId, state: { validation: { status: "passed" }, artifacts: [] } } };
    const page = sandbox(selected, checked, result);
    await page.api.runAnalysis();
    const post = page.requests.find(request => request.options && request.options.method === "POST");
    const payload = JSON.parse(post.options.body);
    assert.equal(payload.delivery_mode === "public_draft", expected);
    assert.equal(payload.public_draft_confirmed === true, expected);
  }
  const ready = sandbox();
  await ready.api.handleAnalysisResult(draftResult(), macroContext);
  assert.equal(ready.nodes.get("pptBtn").disabled, false);
  assert.equal(ready.nodes.get("pptBtn").textContent, "下载草稿PPT");
  assert.equal(ready.api.state.lastQuality.score, undefined);
  assert.equal(ready.api.state.lastQuality.overall_status, "草稿验收通过");
  assert.ok(ready.nodes.get("reportArea").innerHTML.includes("不属于完整正式报告"));
  await ready.api.generatePpt();
  assert.deepEqual(ready.links, [`/api/macro-report/draft/${runId}`]);
  assert.equal(ready.requests.some(request => request.url === "/api/ppt"), false);
  const failed = sandbox();
  const incomplete = draftResult(); incomplete.skill_run.state.draft_validation.status = "failed";
  await failed.api.handleAnalysisResult(incomplete, macroContext);
  assert.equal(failed.nodes.get("pptBtn").disabled, true);
  await failed.api.generatePpt();
  assert.equal(failed.links.length, 0);
  assert.equal(failed.requests.some(request => request.url === "/api/ppt"), false);
  const poll = sandbox();
  const polled = await poll.api.pollMonthlyJob(runId);
  assert.equal(polled.job_status, "draft_ready");
  assert.equal(poll.storage.get("macro-monthly-last-public-draft-run"), runId);
  assert.equal(poll.storage.has("macro-monthly-active-run"), false);
  assert.equal(poll.api.state.activeRunId, null);
  const restored = sandbox(["macro_monthly_report"], true, draftResult(), `?run=${runId}`);
  restored.storage.set("macro-monthly-last-public-draft-run", runId);
  await restored.api.restoreActiveMonthlyJob();
  assert.equal(restored.nodes.get("pptBtn").disabled, false);
  assert.equal(restored.api.state.lastMeta.runId, runId);
  assert.equal(restored.nodes.get("macroPublicDraft").checked, true);
  assert.equal(restored.requests.some(request => request.options && request.options.method === "POST"), false);
  const failedRestore = sandbox(["macro_monthly_report"], true, incomplete, `?run=${runId}`);
  failedRestore.storage.set("macro-monthly-active-run", runId);
  await failedRestore.api.restoreActiveMonthlyJob();
  assert.equal(failedRestore.nodes.get("pptBtn").disabled, true);
  assert.equal(failedRestore.requests.some(request => request.url === "/api/ppt"), false);
  const archive = sandbox(["macro_monthly_report"], true, draftResult(), "?project=example-project");
  await archive.api.loadArchivedProject();
  assert.equal(archive.nodes.get("pptBtn").disabled, false);
  assert.equal(archive.nodes.get("runBtn").disabled, true);
  assert.equal(archive.api.state.lastMeta.runId, runId);
  assert.ok(archive.requests.some(request => request.url === `/api/macro-report/jobs/${runId}`));
  await archive.api.generatePpt();
  assert.deepEqual(archive.links, [`/api/macro-report/draft/${runId}`]);
  const failedArchive = sandbox(["macro_monthly_report"], true, incomplete, "?project=example-project");
  await failedArchive.api.loadArchivedProject();
  assert.equal(failedArchive.nodes.get("pptBtn").disabled, true);
  assert.equal(failedArchive.requests.some(request => request.url === "/api/ppt"), false);

  // Old formal macro projects download only the original completed run artifact.
  const formal = sandbox(["macro_monthly_report"], false, formalResult(), "?project=old-formal&month=2026-09");
  await formal.api.loadArchivedProject();
  assert.equal(formal.api.state.lastMeta.runId, runId);
  assert.equal(formal.api.state.lastMeta.macroDeliveryReady, true);
  assert.equal(formal.nodes.get("pptBtn").disabled, false);
  await formal.api.generatePpt();
  assert.deepEqual(formal.links, [formalResult().skill_run.delivery_url]);
  assert.equal(formal.requests.some(request => request.url === "/api/ppt"), false);
  for (const mutate of [
    r => r.skill_run.state.artifact_validations.pop(),
    r => r.skill_run.delivery_url = "/outputs/ppt/macro-another-run-old.pptx",
    r => r.skill_run.delivery_url = `/outputs/ppt/${runId}-..%2Foutside.pptx`,
    r => r.skill_run.state.formal_delivery_allowed = false,
    r => { delete r.run_id; delete r.skill_run.run_id; },
    r => { r.run_id = "skill-20261003-000000-old"; r.skill_run.run_id = r.run_id; }
  ]) {
    const original = formalResult(); mutate(original);
    const oldProject = sandbox(["macro_monthly_report"], false, original, "?project=old-invalid");
    await oldProject.api.loadArchivedProject();
    assert.equal(oldProject.nodes.get("pptBtn").disabled, true);
    assert.ok(oldProject.nodes.get("reportArea").innerHTML.includes("不会改走通用PPT重新生成"));
    await oldProject.api.generatePpt();
    assert.equal(oldProject.links.length, 0);
    assert.equal(oldProject.requests.some(request => request.url === "/api/ppt"), false);
  }
  const missingJob = sandbox(["macro_monthly_report"], false, formalResult(), "?project=old-missing");
  const previousFetch = missingJob.context.fetch;
  missingJob.context.fetch = async (url, options) => url.startsWith("/api/macro-report/jobs/")
    ? { ok: false, status: 404, async json() { return { error: "原运行记录不存在" }; } }
    : previousFetch(url, options);
  await missingJob.api.loadArchivedProject();
  assert.equal(missingJob.nodes.get("pptBtn").disabled, true);
  assert.ok(missingJob.nodes.get("reportArea").innerHTML.includes("原运行记录不存在"));

  // Reset exits replay mode, restores controls and removes only this replay URL.
  const beforeReset = formal.requests.length;
  await formal.api.runAnalysis();
  assert.equal(formal.requests.length, beforeReset, "Historical keyboard shortcuts must not launch a new task.");
  formal.api.resetPage();
  assert.equal(formal.nodes.get("questionInput").readOnly, false);
  assert.equal(formal.nodes.get("runBtn").disabled, false);
  assert.ok(formal.nodes.get("runBtn").innerHTML.includes("<span>开始分析</span>"));
  assert.equal(formal.nodes.get("macroReportMonth").disabled, false);
  assert.equal(formal.nodes.get("macroPublicDraft").disabled, false);
  assert.equal(formal.nodes.get("macroPublicDraft").checked, false);
  assert.deepEqual(formal.historyRoutes, ["/strategy-analysis.html?month=2026-09&new=1"]);
  assert.equal(formal.api.state.lastMeta, null);
  await formal.api.runAnalysis();
  assert.ok(formal.requests.some(request => request.url === "/api/macro-report/jobs" && request.options.method === "POST"));
  const runningReset = sandbox();
  runningReset.api.state.running = true;
  runningReset.api.state.activeRunId = runId;
  runningReset.api.resetPage();
  assert.equal(runningReset.api.state.running, true);
  assert.equal(runningReset.api.state.activeRunId, runId);
  // A new analysis must not inherit old draft consent, results or an active
  // run owned by another tab. Do not delete those tasks to achieve isolation.
  for (const search of ["?new=1", "?skills=macro_monthly_report&month=2026-09", "?agent=market_strategy", "?plugins=policy"]) {
    const fresh = sandbox([], false, draftResult(), search);
    fresh.storage.set("macro-monthly-last-public-draft-run", runId);
    fresh.storage.set("macro-monthly-active-run", runId);
    await fresh.api.restoreActiveMonthlyJob();
    assert.equal(fresh.requests.length, 0);
    assert.equal(fresh.api.state.lastReport, "");
    assert.equal(fresh.api.state.lastMeta, null);
    assert.equal(fresh.nodes.get("macroPublicDraft").checked, false);
    assert.equal(fresh.storage.get("macro-monthly-active-run"), runId);
  }
  const bare = sandbox([], false);
  bare.storage.set("macro-monthly-last-public-draft-run", runId);
  await bare.api.restoreActiveMonthlyJob();
  assert.equal(bare.requests.length, 0, "Bare entry must not load a completed cached draft.");
  const staleActive = sandbox([], false);
  staleActive.storage.set("macro-monthly-active-run", runId);
  await staleActive.api.restoreActiveMonthlyJob();
  assert.equal(staleActive.api.state.lastMeta, null);
  assert.equal(staleActive.storage.has("macro-monthly-active-run"), false);
  const legacyActive = sandbox(["macro_monthly_report"], true);
  legacyActive.storage.set("macro-monthly-active-run", runId);
  const activeFetch = legacyActive.context.fetch;
  let firstActiveSnapshot = true;
  legacyActive.context.fetch = async (url, options) => {
    if (firstActiveSnapshot && url.includes(`/jobs/${runId}`)) {
      firstActiveSnapshot = false;
      legacyActive.requests.push({ url, options });
      return { ok: true, status: 200, async json() { return { ...legacyActive.job, status: "running" }; } };
    }
    return activeFetch(url, options);
  };
  await legacyActive.api.restoreActiveMonthlyJob();
  assert.equal(legacyActive.api.state.lastMeta.runId, runId);
  assert.ok(legacyActive.context.window.location.search.includes(`run=${runId}`));
  assert.equal(legacyActive.requests.some(item => item.options && item.options.method === "POST"), false);
  const isolated = sandbox([], false, draftResult(), "?new=1&project=old-project");
  await isolated.api.loadArchivedProject();
  assert.equal(isolated.requests.length, 0);
  const ownRun = sandbox(["macro_monthly_report"], false, draftResult(), `?run=${runId}`);
  ownRun.storage.set("macro-monthly-active-run", "macro-another-tab");
  await ownRun.api.restoreActiveMonthlyJob();
  assert.ok(ownRun.requests.every(item => item.url.includes(runId)), "Refresh must target this page's run.");
  const started = sandbox(["macro_monthly_report"], true, draftResult(), "?new=1");
  await started.api.runAnalysis();
  assert.ok(started.context.window.location.search.includes(`run=${runId}`));
  assert.equal(new URLSearchParams(started.context.window.location.search).has("new"), false);

  // Replaying a passenger-car project must retain the archive's exact run ID
  // for PPT release; report prose and another tab's active run are not IDs.
  const passengerRun = "month-20261007-205952-3a1e0d51";
  const passengerResult = { answer: "# 已校验的乘用车月报", run_id: passengerRun,
    formal_delivery_allowed: true, quality: { overall_status: "通过" } };
  const passenger = sandbox(["passenger_car_monthly_report"], false, passengerResult,
    "?project=proj-passenger", "passenger_car_monthly_report");
  passenger.api.state.activeRunId = "month-another-tab";
  await passenger.api.loadArchivedProject();
  assert.equal(passenger.api.state.lastMeta.runId, passengerRun);
  await passenger.api.generatePpt();
  const passengerPost = passenger.requests.find(item => item.url === "/api/ppt");
  assert.ok(passengerPost, "Archived passenger report must reach the PPT API.");
  const passengerPayload = JSON.parse(passengerPost.options.body);
  assert.equal(passengerPayload.run_id, passengerRun);
  assert.equal(passengerPayload.analysis_type, "passenger_car_monthly_report");
  assert.equal(passenger.requests.some(item => item.url === "/api/monthly-report/jobs"), false,
    "Export must not create a new analysis job.");
  const noId = sandbox(["passenger_car_monthly_report"], false,
    { ...passengerResult, run_id: null }, "?project=missing-id", "passenger_car_monthly_report");
  noId.api.state.lastMeta = { runId: passengerRun };
  noId.api.state.activeRunId = passengerRun;
  await noId.api.loadArchivedProject();
  await noId.api.generatePpt();
  assert.equal(noId.api.state.lastMeta.runId, null);
  assert.equal(noId.requests.some(item => item.url === "/api/ppt"), false);
  const blockedPassenger = sandbox(["passenger_car_monthly_report"], false,
    { ...passengerResult, formal_delivery_allowed: false }, "?project=blocked-passenger", "passenger_car_monthly_report");
  await blockedPassenger.api.loadArchivedProject();
  await blockedPassenger.api.generatePpt();
  assert.equal(blockedPassenger.requests.some(item => item.url === "/api/ppt"), false);
  console.log("Public draft UI: offline request, gate, direct-download, refresh and archive assertions passed.");
}
main().catch(error => { console.error(error); process.exitCode = 1; });
