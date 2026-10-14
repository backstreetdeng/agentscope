# Project execution rules

## Complete Skill integration

- Read and follow `docs/skill-integration-standard.md` before adding or changing a Skill integration.
- A Skill is an executable package, not injected `SKILL.md` text. The web agent must receive package-relative access to its manifest, references, assets, scripts, declared dependencies, tools, isolated run workspace, persistent task graph, checkpoints, and validators.
- Do not mark a Skill as integrated until a real representative task produces its required artifact and passes independent acceptance gates.
- Preserve capability parity: if Codex can execute a packaged asset or script that the web agent cannot access, the web integration is incomplete.
- Never claim completion from model prose alone. Completion comes from persisted task state, observable tool evidence, required artifacts, and passing validators.

## Provider credentials

- Credential products are not interchangeable. A Zhipu Coding Plan credential is not a BigModel Open Platform API key and must not be sent to the standalone AgentScope web agent endpoint.
- Keep unavailable providers disabled and show the exact product-scope limitation. Enable a provider only after a compatible API credential passes a real preflight request.
- For Alibaba Cloud Model Studio, a workspace/pay-as-you-go API key paired with its workspace-specific `compatible-mode/v1` Base URL may be used by the web backend after a successful chat-completions preflight.
- The user has explicitly authorized a local webpage validation using an Alibaba Cloud Token Plan key (`sk-sp-`) and `qwen3.7-plus`. Keep it isolated to the local service, record the actual result, and do not claim production eligibility from this validation alone.

## Monthly-report browser session

- Treat the visible Chrome profile at `runtime/monthly-report-browser-profile` as a durable business session after the user completes SMS authentication.
- Never close, kill, relaunch, or replace that dedicated browser merely to restart the web service, retry a tool call, diagnose a task, or end an agent turn.
- Before restarting port 7860, check whether the dedicated browser is running. If it is, preserve it and do not restart the owning service unless the user explicitly authorizes losing that live browser session.
- A browser profile directory or Cookies file existing on disk does not prove that the authenticated session is still valid. Verify the visible BI page without reading credentials.
- After a successful BI-page verification, persist only non-sensitive evidence: Windows account, dedicated profile path, verification time, BI URL, and report month. Never persist copied cookies, passwords, SMS codes, or tokens.
- On a later natural reopen, verify whether the same Windows account and profile return directly to the BI page. Report `login session not restored` when the site redirects to authentication; do not misreport that state as `cards not loaded`.
- Do not close a live dedicated browser merely to test persistence. Perform close/reopen verification only after the user explicitly approves that controlled test or when the browser has already been closed naturally.
