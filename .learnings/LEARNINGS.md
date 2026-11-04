# Learnings

## [LRN-20261008-PAGES] correction

**Logged**: 2026-10-08
**Priority**: critical
**Status**: promoted
**Area**: backend

### Summary
主旨句提升须横向处理各分析页的事实关系与图表支撑；三行是信息密度和版式目标，不能降低为一两行，也不能仅校验数字出现在某张卡片。

### Details
真实8月45/45包复核发现单月/累计、同比/环比和新能源份额分母错配，以及库存总降但新能源库存升被概括为同步去化。逐数字绑定对象、指标、比较期、分母和贡献操作数；分号后的未具名数字不能借同页白名单，三层空泛文字不能凭有效fact_id过关。库存模板第二个非空文本框其实是图表标题，必须使用显式正文角色；五页累计图的同期数量与全年份额旧缓存也须同时纠正。固定期间必须移除动态日期field，不能只改其缓存文字；PowerPoint实际重算曾恢复旧全年标签。完整卡片数量不代表榜单所有行都完整，不能由部分对象称唯一领涨。公开证据不足时只做事实关系，不把不同基期的同比收缩解释为环比份额提升。

### Action
将具名事实、逐页关系草案、语义/三行门禁和精准chart/embed写回接入网页后台同一调用链。升级只重验观点，不重采当月包。保留原始回复、失败原因和局部检查点；模型润色失败时使用同门禁的当月事实稿并明确标记。实际独立全页模型/写回/渲染与新网页完整实跑分别验收，不冒充已运行新网页任务。

2026-10-08验收：16个分析页、21页/39原生图表、实际PowerPoint渲染与独立实图复查通过；网页出口调用同一逐页门禁，服务状态确认加载v5，静态下载200且SHA一致。规则升级不回写历史已完成任务：新版观点新建任务，未完成任务可恢复。原45卡片包哈希保持不变，未重新采集或操作专用浏览器。生产导出离线真实合同与新网页完整实跑分别记录，后者仍由下一次业务任务验收。

### Metadata
- Source: user_feedback
- Related Files: utils/monthly_page_facts.py, utils/monthly_page_narratives.py, utils/monthly_ppt_layout.py, utils/monthly_report_narrative.py
- Pattern-Key: monthly.entity_metric_scope_not_number_whitelist

---

## [LRN-20261004-001] correction

**Logged**: 2026-10-04
**Priority**: critical
**Status**: in_progress
**Area**: backend

### Summary
Skill 能力来自每次运行时完整操作知识、资源和真实工具的配合，不是模型训练；采集器 missing 不等于没有公开数据。

### Details
用户要求重新核对宏观业务完整包和 WorkBuddy 能力。原包六个文件均已检查，原 PPT 模板与网页包 SHA256 一致，原包没有 scripts。当前通用 Runtime 确实提供完整包访问，不能再声称仅加载 SKILL.md；但宏观专用采集是固定流程，目录候选存在但抓取/抽取失败时缺少失败驱动补证。公开草稿仅用确定性 reader，reader 缺项不证明数据不存在。真实运行 macro-20261004-174645-0d26dcc2 为 draft_ready、99/134；这不是完整业务能力等价。

ISM 美国 PMI 的官方可读页面有9月值与历史表。当前运行保存的该 URL 实际重定向到 ecommerce.ismworld.org/SSO/Login.aspx，却记为 publication_date_unverified；只读直接探测又返回404。这首先是访问路径和错误分类问题，不能简化成“统计数据未发布”或“DOM日期解析错误”。不允许绕过授权限制或将检索摘要直接写入正式数据。

### Suggested Action
按精确指标建立可恢复的检索—读取—验收—改策略循环。区分未发布、授权要求、传输失败、解析未命中、口径不符；真实工具结果决定下一步。对现有35项定向补证并保留99项已验数据。审查原包“最新已发布实际期/无用户要求不预测”与当前 forecast 默认适配的差异，结合已有业务授权对齐，不能悄悄切换。

### Metadata
- Source: user_feedback, project_audit, official_documentation, read_only_live_probe
- Related Files: skills/macro-monthly-report/scripts/macro_sources.py, skill_runtime/core.py, .work/macro-skill-audit-20261004/audit.json
- Pattern-Key: skill.runtime_capability_parity_and_failure_driven_research

---

## [LRN-20261003-001] best_practice

**Logged**: 2026-10-03T15:40:00+08:00
**Priority**: critical
**Status**: in_progress
**Area**: backend

### Summary
模板基准稿通过文件检查，不能替代权威取数和逐页业务验收。

### Details
宏观运行 skill-20261003-152013-a6da7bb1 仅调用模板内嵌历史预测脚本，模型却声称已检索最新权威数据；前端进一步将结构通过显示为业务100分。修正交付说明必须以落盘台账为依据，明确基准稿和未完成的业务环节，不用用户请求代替执行证据。

### Suggested Action
后续补齐宏观权威取数、预测验证与逐页正文更新；在此之前仅保留技术检查通过，业务验收阻断。误导性交付说明、前端100分误判和错误正式下载已修正，15项回归测试通过，在线接口拒绝旧下载和重新导出；业务内容修复仍未完成。

### Metadata
- Source: error
- Related Files: app.py, utils/macro_report_delivery.py, assets/strategy-analysis.js
- Pattern-Key: harden.evidence_bound_delivery

---

## [LRN-20260928-004] correction

**Logged**: 2026-09-28T00:00:00+08:00
**Priority**: high
**Status**: wont_fix
**Area**: backend

### Summary
Forecast-year completion must follow the business data status, not the local system date.

### Details
The user confirmed that 2026 has ended and should be treated as a complete historical year. The previous implementation inferred year completeness from the local date and incorrectly described 2026 as unfinished. The confirmed 1,960万辆 is therefore a complete 2026 annual historical total, while 2,060万辆 remains the user-confirmed 2027 forecast constraint. A complete annual total still does not imply that monthly actuals have been supplied.

### Suggested Action
Pass explicit business period status into forecast prompts and keep annual-history completeness separate from monthly-data completeness.

### Metadata
- Source: user_feedback
- Related Files: assets/home.js, home.html, agents/market_strategy_agent.py
- Tags: market-forecast, cutoff-date, historical-year, annual-constraint

### Resolution
- **Resolved**: 2026-09-28T00:00:00+08:00
- **Notes**: Superseded by LRN-20260928-005. The user's statement was based on a mistaken belief that the current year was 2027; the actual current date is 2026-09-28.

---

## [LRN-20261001-001] knowledge_gap

**Logged**: 2026-10-01T00:00:00+08:00
**Priority**: critical
**Status**: promoted
**Area**: config

### Summary
Successful API authentication does not override the commercial product scope of an Alibaba Cloud Model Studio credential.

### Details
The workspace API key succeeded against its Beijing workspace-specific OpenAI-compatible endpoint and completed a minimal `qwen-plus` chat request, so it is suitable for a web-agent backend. The Token Plan `sk-sp-` key also listed models and completed a minimal `qwen3.7-plus` chat request at the Token Plan endpoint. However, Alibaba Cloud documentation restricts Token Plan to interactive AI tools such as Codex and Claude Code and explicitly says it cannot be used for backend services. Therefore technical reachability and backend authorization must be evaluated separately.

### Suggested Action
For each provider, validate key prefix/product, matching Base URL, `/models`, one minimal generation request, and documented deployment scope. Use the workspace key for this web backend; reserve Token Plan credentials for supported interactive AI tools.

### Metadata
- Source: user_feedback, external_api_test
- Related Files: model_config/config.json, AGENTS.md, docs/skill-integration-standard.md
- Tags: aliyun, bailian, token-plan, workspace-key, provider-auth, backend
- Pattern-Key: provider.validate_credential_product_scope
- Recurrence-Count: 3
- First-Seen: 2026-09-30
- Last-Seen: 2026-10-01
- See Also: LRN-20260930-005

### Resolution
- **Resolved**: 2026-10-01T00:00:00+08:00
- **Notes**: Verified both endpoints with real model listing and minimal chat requests, then promoted the product-scope distinction to project rules.
- **Promoted**: AGENTS.md, docs/skill-integration-standard.md

---

## [LRN-20260930-005] correction

**Logged**: 2026-09-30T22:30:00+08:00
**Priority**: high
**Status**: resolved
**Area**: config

### Summary
Do not treat a Zhipu Coding Plan credential as a normal BigModel Open Platform API key in a standalone AgentScope process.

### Details
The workbench exposed Zhipu GLM as an OpenAI-compatible provider and sent the configured Coding Plan credential to `open.bigmodel.cn/api/paas/v4/`. The resulting `429 / 1113` was initially described as ordinary account balance exhaustion. The user clarified that the credential belongs to Zhipu Coding Plan and is not authorized for direct use by an independent AgentScope script, so the call is not a valid comparison of model output or JSON compliance.

### Suggested Action
Keep this provider disabled in the standalone workbench until a BigModel Open Platform API key is configured. Reject the provider before execution with an explicit capability-boundary message; do not infer model behavior from the resulting authorization/quota error.

### Metadata
- Source: user_feedback
- Related Files: model_config/config.json, strategy-analysis.html, app.py
- Tags: zhipu, coding-plan, agentscope, provider-auth, error-classification
- Pattern-Key: provider.validate_credential_product_scope
- Recurrence-Count: 2
- First-Seen: 2026-09-30
- Last-Seen: 2026-10-01

### Resolution
- **Resolved**: 2026-09-30T22:30:00+08:00
- **Notes**: Disabled the misleading UI option and added backend validation with a precise remediation message.

---

## [LRN-20260929-003] correction

**Logged**: 2026-09-29T23:05:00+08:00
**Priority**: critical
**Status**: resolved
**Area**: backend

### Summary
Do not infer a transport deadlock from a long MCP tool wait; isolate connect, discovery, browser initialization, and page navigation before changing architecture or timeouts.

### Details
The initial symptom was a 360-second AgentScope MCP timeout. Treating it as a slow 45-card read or a Windows stdio problem was premature. A bounded direct probe proved that `connect` and `list_tools` were healthy under both stdio and HTTP, while `browser_tabs` triggered a Chrome crash. Playwright MCP 0.0.82 did not promptly turn that browser exit into a tool error, so the client appeared to hang. Debugging the server process and browser stderr revealed the actual GPU/sandbox crash and a second writable-cache issue.

The user also correctly required business correctness before performance tuning: internal card DOM must remain local, only page-level minimum facts may be sent to the selected model, and the final goal is a verified PPT rather than a pipeline demonstration.

### Suggested Action
For browser MCP incidents, always run the checked-in minimal probe in this order: connect, list_tools, browser_tabs, snapshot, navigate, snapshot. Compare stdio with HTTP only after the same browser arguments and writable directories are used. Treat longer timeouts as protection, never as a fix. For monthly reports, judge completion by the produced and verified PPT, not by intermediate workflow messages.

### Metadata
- Source: user_feedback
- Related Files: scripts/probe_playwright_mcp.py, tools/monthly_report_browser.py, utils/monthly_report_narrative.py, app.py
- Tags: mcp, playwright, windows, diagnosis, data-minimization, business-outcome
- Pattern-Key: harden.browser_mcp_layered_diagnosis

### Resolution
- **Resolved**: 2026-09-29T23:05:00+08:00
- **Notes**: Added bounded transport/browser probes, fixed the Windows MCP launch environment, preserved the local read-only browser fallback, and documented the business acceptance criterion.

---

## [LRN-20260928-003] correction

**Logged**: 2026-09-28T00:00:00+08:00
**Priority**: high
**Status**: resolved
**Area**: frontend

### Summary
Annual market forecasts must be supplied or explicitly confirmed by the user; the UI must not introduce an external annual figure as a forecast input.

### Details
An earlier market-prediction view rendered a 2018 annual total sourced from public data. The business skill requires the initial annual constraint to be user-provided, so that value was out of scope and made the screen look like a static demo.

### Suggested Action
Expose annual totals as a confirmed input, require same-caliber monthly history before producing a new monthly path, and preserve input provenance in the result.

### Metadata
- Source: user_feedback
- Related Files: home.html, assets/home.js
- Tags: market-forecast, annual-constraint, provenance

### Resolution
- **Resolved**: 2026-09-28T00:00:00+08:00
- **Notes**: Replaced the static-only flow with a conversational forecast workspace, injected the business-owned Skill into market-forecast requests, preserved the user-confirmed 2026/2027 annual constraints, and added task/version provenance.

---

## [LRN-20260928-005] correction

**Logged**: 2026-09-28T00:00:00+08:00
**Priority**: critical
**Status**: resolved
**Area**: backend

### Summary
Do not accept a temporal assertion that conflicts with the known current date without surfacing the contradiction.

### Details
The user first stated that 2026 had ended because they mistakenly believed the current year was 2027. The assistant adopted that claim and rewrote the forecast status, despite the environment date being 2026-09-28. Correctly, 2026 is still in progress; 1,960万辆 is an annual forecast/adopted constraint, not a completed historical actual.

### Suggested Action
For forecast period status, cross-check user wording against the current date and data cutoff. If they conflict, explain the conflict and ask for clarification before changing historical/forecast classifications.

### Metadata
- Source: user_feedback
- Related Files: assets/home.js, home.html, agents/market_strategy_agent.py
- Tags: temporal-consistency, cutoff-date, forecast-status
- See Also: LRN-20260928-004

### Resolution
- **Resolved**: 2026-09-28T00:00:00+08:00
- **Notes**: Restored 2026 to current-year forecast status and added an explicit date-conflict rule to the forecast agent and request context.

---

## [LRN-20260921-001] Local preview may have multiple stale listeners

**Logged**: 2026-09-21
**Context**: New-car detail page API verification

When a local route intermittently serves old and new responses, inspect all PIDs listening on the preview port before debugging application code. Multiple Python processes were bound to `127.0.0.1:7860`, so requests were distributed across stale server instances and the new `/api/new-car/planned` endpoint appeared to fail randomly. After verifying each listener was the expected Python service, stop the stale instances and keep one server process.

**Practical rule**: After restarting this preview, verify there is exactly one listener on port 7860 and test both data endpoints before UI QA.

**Recurrence-Count**: 2  
**Last-Seen**: 2026-09-28 — 新增口碑下钻接口时再次发现两个 Python 监听器，导致请求随机命中旧进程并返回 404；清理全部经核验的 Python 监听进程后恢复。

---

## [LRN-20260928-002] best_practice

**Logged**: 2026-09-28T00:00:00+08:00
**Priority**: medium
**Status**: pending
**Area**: frontend

### Summary
Restart the local service after editing HTML files that `app.py` reads into module-level constants.

### Details
`NEW_CAR_DETAIL_HTML` is populated once when `app.py` imports. Editing `new-car-detail.html` does not change the running response until the Python service restarts. Browser reloads alone can therefore keep showing old markup.

### Suggested Action
After editing `home.html`, `legacy_workbench.html`, `strategy-analysis.html`, or `new-car-detail.html`, run `scripts/start_agent.ps1`, verify a single listener on port 7860, and use a cache-busted preview URL for UI validation.

### Metadata
- Source: error
- Related Files: app.py, new-car-detail.html, scripts/start_agent.ps1
- Tags: preview, restart, html-cache
- See Also: LRN-20260921-001

---
## [LRN-20260928-001] correction

**Logged**: 2026-09-28T00:00:00+08:00
**Priority**: high
**Status**: superseded
**Area**: backend

### Summary
The macro-economic monthly-report skill was initially interpreted as using one canonical rolling business ledger.

### Details
This interpretation was later corrected: the Skill's “data ledger” is an agent-created working audit ledger generated during each run, not a business-maintained prerequisite workbook.

### Suggested Action
See LRN-20260930-001 and remove the mandatory business-ledger upload gate.

### Metadata
- Source: user_feedback
- Related Files: assets/strategy-analysis.js, app.py
- Tags: macro-monthly, single-ledger, workflow-scope
- See Also: LRN-20260930-001

---

## [LRN-20260930-001] correction

**Logged**: 2026-09-30T00:00:00+08:00
**Priority**: high
**Status**: pending
**Area**: backend

### Summary
The macro monthly Skill's data ledger is an internal execution artifact, not a business-uploaded input requirement.

### Details
“Start every update with a data ledger” instructs the agent to inventory each data-bearing slide and record indicator, definition, unit, source, latest period, old/new values, and affected elements before editing the PPT. Business users may directly request a monthly update; the agent must create this working ledger itself while collecting authoritative data.

### Suggested Action
Remove the mandatory ledger-upload gate from the macro monthly UI. Let the user specify the report month and run directly. Create and retain the audit ledger inside the task execution record, optionally exposing it as evidence after completion.

### Metadata
- Source: user_feedback
- Related Files: skills/macro-monthly-report/SKILL.md, assets/strategy-analysis.js, strategy-analysis.html, app.py
- Tags: macro-monthly, audit-ledger, workflow-scope
- See Also: LRN-20260928-001

---
## [LRN-20260929-001] correction

**Logged**: 2026-09-29T13:20:00+08:00
**Priority**: medium
**Status**: resolved
**Area**: config

### Summary
Dotenv configuration helpers must verify the persisted file instead of assuming an in-memory collection mutation was saved.

### Details
The MCP configuration script reported that `.env` had been written, but the user correctly observed that neither `MARKET_MCP_BASE_URL` nor `MARKET_MCP_API_TOKEN` was present afterward.

### Suggested Action
Write configuration atomically, remove duplicate target keys, and immediately read the file back to require exactly one occurrence of each key before starting remote verification.

### Metadata
- Source: user_feedback
- Related Files: scripts/configure_market_mcp.ps1
- Tags: powershell, dotenv, verification

### Resolution
- **Resolved**: 2026-09-29T13:20:00+08:00
- **Notes**: Replaced the collection-mutating helper with atomic rewrite and persisted-key validation; verified against a temporary dotenv file.

---
## [LRN-20260929-002] correction

**Logged**: 2026-09-29T13:30:00+08:00
**Priority**: medium
**Status**: resolved
**Area**: config

### Summary
Re-check mutable configuration immediately before reporting its current state.

### Details
An earlier inspection observed an empty MCP token, but the configuration changed afterward. Reporting the older observation as current was incorrect; the user confirmed the token was populated.

### Suggested Action
For `.env` and other mutable runtime configuration, perform a fresh masked check at response time and distinguish historical findings from current state.

### Metadata
- Source: user_feedback
- Related Files: .env, scripts/configure_market_mcp.ps1
- Tags: configuration, freshness, verification

### Resolution
- **Resolved**: 2026-09-29T13:30:00+08:00
- **Notes**: Fresh masked verification confirmed one non-empty 64-character token and live MCP status of 4/4 ready with 27 tools.

---

## [LRN-20260930-002] correction

**Logged**: 2026-09-30T17:35:00+08:00
**Priority**: high
**Status**: in_progress
**Area**: backend

### Summary
After isolating a production-blocking cause in an ongoing business test, continue directly into the in-scope fix instead of stopping at a diagnosis-only handoff.

### Details
The monthly report run exposed 45 detected cards but only 24 cards passing freshness validation. The first response correctly separated virtual-scroll capture gaps from freshness-rule false negatives, but stopped after reporting the diagnosis even though the surrounding task was an active implementation-and-validation workflow. The user had to explicitly ask to continue.

### Suggested Action
When a user is actively validating an already-authorized implementation, treat a diagnosed defect as part of the same repair loop: patch the narrow cause, run targeted tests, restart the service if needed, and verify against the live run before handing control back.

### Metadata
- Source: user_feedback
- Related Files: tools/monthly_report_browser.py, app.py, tests/test_monthly_report_browser.py
- Tags: monthly-report, repair-loop, virtual-scroll, freshness-gate
- Pattern-Key: workflow.continue_after_in_scope_diagnosis
- Recurrence-Count: 1
- First-Seen: 2026-09-30
- Last-Seen: 2026-09-30

---

## [LRN-20260930-003] correction

**Logged**: 2026-09-30T20:00:00+08:00
**Priority**: critical
**Status**: pending
**Area**: backend

### Summary
The macro-economic monthly report is a forecast workflow; unavailable future-month observations are expected outputs to forecast, not completeness failures.

### Details
The target report month defines the forecast horizon. The agent should use the latest officially available historical observations as the information cutoff, then generate forecast values and clearly label actual versus forecast periods. It must not block merely because target-month CPI, PPI, consumption, investment, trade, or auto-market actuals have not yet been released. Data gates apply to the historical baseline, source traceability, definition consistency, model assumptions, and template execution—not to the existence of future actuals.

### Suggested Action
Split the Skill into forecast and historical-update semantics. For a current or future target month, forecast missing target-period values with explicit assumptions, intervals/scenarios, and actual/forecast labels. Block only when the historical baseline, definitions, model inputs, or template assets are insufficient to make a defensible forecast.

### Metadata
- Source: user_feedback
- Related Files: skills/macro-monthly-report/SKILL.md, assets/strategy-analysis.js, app.py
- Tags: macro-monthly, forecast, data-gate, actual-vs-forecast
- See Also: LRN-20260930-001

---

## [LRN-20260930-004] correction

**Logged**: 2026-09-30T20:10:00+08:00
**Priority**: critical
**Status**: promoted
**Area**: backend

### Summary
A Skill integration must expose the complete package and its runtime dependencies; injecting only `SKILL.md` text is not a Skill execution.

### Details
The macro monthly package already contains `artifact-template.json`, `assets/reference.pptx`, `assets/preview.png`, and `references/data-and-qa-rules.md`. The web backend loaded only Markdown into the model prompt, so the agent incorrectly reported that the retained template was unavailable even though it existed on disk. Codex succeeds because it can resolve the package-relative assets and use presentation/file tooling. The web agent must receive an equivalent package-aware runtime, not a weaker prompt-only imitation.

### Suggested Action
Replace the prompt-only loader with a package loader that validates the manifest, resolves and exposes assets, loads relevant references, and mounts deterministic presentation/file tools or a dedicated executor. Fail before model execution if required package assets or runtime dependencies are unavailable.

### Metadata
- Source: user_feedback
- Related Files: skills/macro-monthly-report/, app.py, agents/market_strategy_agent.py, tools/custom_tools.py
- Tags: skill-runtime, package-assets, prompt-only, capability-parity
- See Also: LRN-20260930-001, LRN-20260930-003
- Pattern-Key: skill.complete_package_runtime_parity
- Recurrence-Count: 2
- First-Seen: 2026-09-30
- Last-Seen: 2026-10-01

### Resolution
- **Resolved**: 2026-10-01T00:00:00+08:00
- **Notes**: Implemented the complete-package Skill Runtime and promoted the invariant to `AGENTS.md` and `docs/skill-integration-standard.md` as a mandatory gate for every future Skill integration.
- **Promoted**: AGENTS.md, docs/skill-integration-standard.md

---
## [LRN-20261002-001] correction

**Logged**: 2026-10-02T00:20:00+08:00
**Priority**: high
**Status**: resolved
**Area**: frontend

### Summary
不能仅凭后台任务文件显示 completed 就向用户宣告网页任务完成，必须同时确认前端已成功取回最终状态。

### Details
月报后台任务在服务重启后通过检查点恢复并最终完成，但浏览器轮询在服务短暂离线时收到 `Failed to fetch`，随后将页面标记为未完成。此前只核对了持久化任务状态，忽略了前端交付状态，导致错误地告诉用户界面已经可以使用。

### Suggested Action
完成判断应同时核对后台持久化状态、7860 服务可用性和前端轮询结果；月报轮询遇到临时网络中断时保留同一 run_id 自动重连，不得直接转为业务失败。

### Metadata
- Source: user_feedback
- Related Files: assets/strategy-analysis.js, runtime/monthly-report-jobs/month-20261001-235244-039e8b6a.json
- Tags: monthly-report, polling, service-restart, frontend-state

### Resolution
- **Resolved**: 2026-10-02T00:20:00+08:00
- **Notes**: 前端月报轮询已增加临时断连识别、自动重连和检查点恢复提示。

---

## [LRN-20261003-002] best_practice

**Logged**: 2026-10-03T18:05:00+08:00
**Priority**: critical
**Status**: promoted
**Area**: backend

### Summary
宏观月报必须分别证明真实来源、经济口径、原生图表和实际版式；合成数据及 PowerPoint 可打开不能代替正式报告验收。

### Details
本轮以合成稿验证了图表与版式机制，也以公开原文单独验证了中国 PMI 和 CPI 类别取数。两种证据只能证明各自范围，不能合并宣告全部来源已齐备。CPI 的食品行、食品烟酒餐饮行、单月同比、环比和累计列必须按原始表格独立重放。Office 检查需要隔离用户会话，验收结果与最终文件哈希绑定。

### Suggested Action
保持完整真实数据包验收与结构诊断分离；通过逐来源重放、GDP 与累计预测一致性检查、原生数据校验、实际 Office 和版式四道门禁后才允许发布。

### Metadata
- Source: task_execution
- Related Files: skills/macro-monthly-report/SKILL.md, skills/macro-monthly-report/references/data-and-qa-rules.md, app.py
- Pattern-Key: macro.business_acceptance_not_structural_success
- Promoted: skills/macro-monthly-report/references/data-and-qa-rules.md

---

## [LRN-20261003-003] correction

**Logged**: 2026-10-03T23:10:00+08:00
**Priority**: critical
**Status**: pending
**Area**: backend

### Summary

宏观月报中的 Wind 等标签是数据来源或原始生产者，不等于业务用户必须提供该供应商接口；先复核 Skill 的公开取数方案并实际执行，再判断逐指标缺口。

### Details

用户要求把可由 Codex 运行的 Skill 移植到网页智能体，且没有 Wind 访问方式。原执行器只接受少数原站域名、忽略定向检索计划且不读公开 PDF，实际扩大了 Skill 中“优先原发布、必要时可信转载互证”的要求。完整公开实跑显示仅9/134项通过，证明现有实现不足，不能将该结果归因于用户没有商业账号。已经直接核验统计局、央行、财政部当前及历史正文，并找到高频公开周报候选。

2026-10-04补充：公开网页、原始PDF、发布目录、原文表格确定性读取和来源独立复核已接入同一Skill包。真实网页任务macro-20261004-005541-c8ad8701取得62/134项、355条观测，未触发Wind登录，状态仍needs_repair且无正式PPT。后续房地产与金融同比组件的真实原文回放另行记录，不回写旧任务或冒充升级后的完整网页实跑。央行空“文章来源”被误判转载的问题已修，真实中英及其他文字的外部署名仍必须拒绝。模板基建、商品房待售、服装等口径差异需要明确授权，不能静默替换；剩余解析/历史不足也不能全部归因于这些待确认项。

2026-10-04再次纠偏：单次搜索/抓取失败不能等同公开数据不存在；应按指标核对目录、历史原文、原始附表、发布日期与传输问题，区分“原文已找到但读取器缺失”“后台传输不通”“真正口径冲突”。本次直接重抓统计局/财政部六篇原文成功，财政及投资/汽车利润10项、30个近期请求-观测期已通过独立原文复放。GDP季度、海关和国际PMI另列独立任务，不将其进展混称正式PPT完成；只跑新增指标组的冷启动集成，避免反复重跑整134项而没有交付增量。旧诊断的JSON载荷哈希与正文SHA算法不同只能在验证算法一致后迁移诊断副本，不能覆盖原记录或通过重算哈希掩盖篡改。

2026-10-04功能优先复核：新增42项指标真实冷启动采集与二次原文重放通过；旧网页回执与新真实回执的隔离全量重审得到100/134项、388条观测，但这不等于新网页完整月报通过。PMI多层合并表头曾把总指数列当新订单，现由专用表头展开读取器修复，不平均冲突数值。用户要求先能用，故新增显式选择的公开数据草稿路径；默认正式报告不降级，草稿只用已核验实际，未取证图表为空且不做预测。模板有百万行嵌入工作簿和隐藏filtered-series缓存，草稿改为精简新工作簿并清除旧可见数值及缓存，不能靠全量逐格清空拖慢更新。PowerPoint实机可打开与渲染只是文件门禁，网页任务/可下载/草稿口径仍分别验收；禁止把本地诊断草稿称为正式完整报告。

2026-10-04真实网页基础交付验收：首次草稿任务已取得99/134项并生成文件，但版式验收脚本误用working作为run根目录，导致查找working/outputs和报告写入working/working；已改为优先显式run_root或SKILL_RUN_ROOT，并加入工作目录回归测试。没有篡改失败任务或混用升级前检查点。新版同一包任务macro-20261004-105927-8d681373于10:59:27启动、11:05:00达到draft_ready：84个原文回执、376条观测、99/134项，33页、37个原生图表、2张表格，真实业务、结构、PowerPoint打开/33页渲染/重开及版式均通过。正式完整性未宣称通过，35项缺口保留、没有预测。专用下载HTTP 200与已验收PPT SHA一致；真实点击网页“下载草稿PPT”成功落用户Downloads，并独立复核哈希一致。基础公开数据草稿可用和正式完整月报仍未齐备必须分别向用户说明。

### Suggested Action

把公开主源、可信转载及来源身份独立建模，按年月和频率定向取证；最新转载观测交叉核验。保留精确口径、不绕过登录/付费墙，不用同名异口径替换。以同一包的真实完整执行结果验证网页能力，不能用合成验收或仅修改流程说明宣告移植完成。

### Metadata

- Source: user_feedback
- Related Files: skills/macro-monthly-report/scripts/macro_sources.py, skills/macro-monthly-report/references/source-queries.json, .work/macro-public-run/codex-run-v1/execution.json
- Pattern-Key: macro.provider_label_not_access_prerequisite

---

## [LRN-20261007-BSR] correction

**Logged**: 2026-10-07
**Priority**: high
**Status**: promoted
**Area**: infra

### Summary

专用浏览器曾能在有效期内重开并自动回到 BI，不能把本次回到短信认证入口直接归因为关浏览器或自然过期。

### Details

用户确认下午登录成功，而且以前关闭后重开同一专用 Chrome 可自动返回 BI。2026-10-07 16:03:36 预检保存了仪表板，17:14:37 已只有“登录”。随后检查确认旧 7860 服务及专用 Chrome 属于 CodexSandboxOffline；经用户授权，18 点后将服务启动在桌面账号 11489。同一专用 profile 路径和源仪表板 URL 未变，但当前仍未确认有效认证会话。启动账号切换是已证实的环境差异，不足以单独证明 Cookie 删除、过期或解密失败。原配置目录存在只能证明文件保留，不能宣称登录状态已恢复。

### Suggested Action

复用窗口前先核对进程账号、配置路径、实际跳转网址和页面就绪状态；保留源网址与认证入口的区别。重启前记录启动账号，优先沿用桌面账号和已登录窗口。避免重复重启、复制/读取凭据、绕过短信认证或从旧数据包伪造当前登录成功。历史服务启动记录未记录账号时，应明确缺少证据，不能断言之前的进程身份。

### Metadata

- Source: user_feedback
- Related Files: tools/monthly_report_browser.py, scripts/start_agent.ps1, scripts/restart_desktop_service.py
- Pattern-Key: browser.profile_exists_not_authenticated
- Promoted: AGENTS.md

### Resolution

- **Resolved**: 2026-10-07
- **Notes**: 已将“短信登录后的月报专用浏览器不得因服务重启、任务重试或排查而关闭”写入项目规则；启动脚本默认检测并阻断会关闭专用浏览器的重启，月报步骤重试默认不再关闭浏览器，服务退出也不再显式关闭该浏览器。

## [LRN-20261009-001] correction

**Logged**: 2026-10-09
**Priority**: high
**Status**: resolved
**Area**: backend

### Summary
不能把业务有意选择的全年结构参照改为同比同期，也不能给无正文页面强加三行正文。

### Details
此前将第7/8/12/13/15页右侧2025全年份额误改成1—8月同期值，且库存页新增正文并缩短图表。用户澄清：这五页用全年作为结构参照，第17页才是同期累计；第5页仅页标题与图表标题。六份业务月报按主题对应核对后，已确认这些区别。不能从统一统计习惯或“每页三行”偏好推断授权改变业务版式。

### Resolution
删除通用同期修图，按页面角色只读验收全年参照及同期累计；库存页本地生成标题，不生成模型正文，保留图表原位置/尺寸和标题。新增负例回归，更新Skill，保留历史产物与45/45数据包。

### Metadata
- Source: user_feedback
- Related Files: utils/monthly_ppt_layout.py, utils/monthly_report_narrative.py, skills/market-analysis-skill/passenger-car-monthly-report/references/page-business-support.md
- Pattern-Key: presentation.preserve_business_comparison_and_roles

---
