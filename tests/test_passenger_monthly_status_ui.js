"use strict";
const fs = require("node:fs");
const vm = require("node:vm");
const path = require("node:path");
let harness = fs.readFileSync(path.join(__dirname, "test_macro_public_draft_ui.js"), "utf8");
harness = harness.slice(0, harness.indexOf("async function main()"));
harness = harness.replace("pollMonthlyJob, restoreActiveMonthlyJob", "renderPassengerRunSummary, handleAnalysisError, updateStep, pollMonthlyJob, restoreActiveMonthlyJob");
harness = harness.replace("classList: { add() {}, remove() {} }", "classList: { values: new Set(), add(...names) { names.forEach(n => this.values.add(n)); }, remove(...names) { names.forEach(n => this.values.delete(n)); }, contains(n) { return this.values.has(n); } }");
const checks = `
async function passengerChecks() {
  const id = "month-20261009-000000-1234abcd";
  const blocked = {run_id:id, answer:"卡片已读取，目标9月但库存最新8月", skill:{analysis_type:"passenger_car_monthly_report", output_gate:"数据源门禁阻断", source_package:{code:"data_package_incomplete", report_month:"2026-09", cards_expected:45, cards_captured:45, cards_usable:30}}};
  const s = sandbox(["passenger_car_monthly_report"], false, blocked, "", "passenger_car_monthly_report");
  s.api.renderPassengerRunSummary({run_id:id,report_month:"2026-08",collection_mode:"reuse",cards_reused:45,cards_collected:0});
  const summary=s.nodes.get("passengerRunSummary");
  assert.equal(summary.hidden,false);
  for (const text of ["2026-08","复用已有数据","45","本次采集 0 张"]) assert.ok(summary.textContent.includes(text));
  s.job.run_id=id; s.job.status="input_required"; s.job.recoverable=true; s.job.message="月份未齐";
  let error;
  try { await s.api.pollMonthlyJob(id); } catch(e) {error=e;}
  assert.equal(error.code,"data_package_incomplete");
  assert.equal(error.result,blocked);
  assert.equal(error.runId,id);
  const context={monthlyEnabled:true,analysisType:"passenger_car_monthly_report",selected:["passenger_car_monthly_report"]};
  s.api.updateStep("report","done","old");
  s.api.handleAnalysisError(error,context);
  assert.equal(s.nodes.get("pptBtn").disabled,true);
  assert.equal(s.nodes.get("status-report").textContent,"待执行");
  assert.equal(s.nodes.get("status-quality").textContent,"阻断");
  assert.equal(s.nodes.get("step-report").classList.contains("done"),false);
  assert.ok(s.nodes.get("reportArea").innerHTML.includes(blocked.answer));
  await s.api.handleAnalysisResult({...blocked,job_status:"completed"},context);
  assert.equal(s.nodes.get("status-report").textContent,"待执行");
  for (const month of ["2026-08",""]) {
    const r=sandbox(["passenger_car_monthly_report"],false,blocked,"","passenger_car_monthly_report");
    r.job.run_id=id; r.job.status="input_required"; r.job.recoverable=true;
    r.context.document.getElementById("passengerReportMonth").value=month;
    await r.api.runAnalysis();
    const request=r.requests.find(x=>x.url==="/api/monthly-report/jobs");
    assert.ok(request,"month job submitted");
    const payload=JSON.parse(request.options.body);
    assert.equal(payload.report_month,month || undefined);
  }
  console.log("Passenger monthly UI: month request, reuse counts, blocked diagnostics and legacy false-completion checks passed.");
}
passengerChecks().catch(e=>{console.error(e);process.exitCode=1;});
`;
vm.runInNewContext(harness + checks,{require,__dirname,console,process,URLSearchParams});
