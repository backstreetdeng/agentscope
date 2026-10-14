# 错误与修复记录

## [ERR-20261008-HQA] horizontal_semantics_acceptance

**Logged**: 2026-10-08
**Priority**: high
**Status**: resolved
**Area**: backend

### Summary
全页复核发现累计零售scope被“零售”覆盖、分号截断漏掉未具名数字以及“占全部新能源”被误识别为新主语。首轮模型稿未发布。

### Resolution
明确期间词优先于度量词；只截断泛指方向说明，不截断数字校验；份额分母中的实体不作为新主语，记录实际绑定的度量区间并拒未解析指标。另以反例测试拒有效事实ID加空泛三层正文。空事实包在模型调用前拒绝，三次模型失败的既有测试用正确fixture独立验证。

### Tooling
Windows文件搜索不能把路径glob直接交给rg；改用目录和-g过滤。补丁先核对精确上下文，失败后检查是否落盘，不把验证失败当作改动成功。

---

## [ERR-20261008-S03] targeted_ppt_text_update

**Logged**: 2026-10-08
**Priority**: medium
**Status**: resolved
**Area**: backend

### Summary
三页主旨句验收发现非目标页XML重新序列化以及前缀替换重复字问题，未发布失败产物。

### Error
`AssertionError: Unrequested slide 3 changed`；`同比正增长`被前缀替换成`同比增长长`。

### Context
python-pptx重存将空文本节点重新序列化，虽未改变非目标页的业务文字，也不符合仅更新指定页面的验收契约。

### Resolution
文本更新保留原ZIP部件，只替换明确指定页面XML。措辞规范化使用完整短语匹配并检查幂等性。增加独立回归，验收时逐项比较图表、嵌入工作簿及非目标页面字节。

### Metadata
- Reproducible: yes
- Related Files: utils/monthly_report_narrative.py, tests/test_monthly_report_narrative.py

---

## [ERR-20261003-001] monitor_endpoint_discovery

**Logged**: 2026-10-03T15:40:00+08:00
**Priority**: low
**Status**: resolved
**Area**: tests

### Summary
监测时误以为GET /api/monthly-report/jobs支持任务列表，实际要求run_id。

### Error
GET /api/monthly-report/jobs returned HTTP 404.

### Suggested Fix
调用前阅读路由；当前宏观任务应核对Skill工作区、归档项目与服务状态，不能使用乘用车后台接口假定宏观可恢复。

### Metadata
- Related Files: app.py
- Reproducible: yes

---

## [ERR-20261001-002] monthly_evidence_non_json_aborted_job

**Logged**: 2026-10-01T23:20:00+08:00
**Priority**: critical
**Status**: resolved
**Area**: backend

### Summary
月报第2批多源取证返回非完整JSON时，未经过重试便终止整个后台任务；前端又把结构化错误显示成`[object Object]`。

### Error
```text
ValueError: 模型返回内容无法解析为JSON对象：未找到完整的JSON对象
ERROR: [object Object]
```

### Context
- run_id: `month-20261001-215647-95239f3c`
- 45/45张卡片和第1批主旨句已经完成。
- 主旨句阶段已有三次结构重试，但其前置多源取证阶段没有重试、诊断文件或安全降级。
- 任务查询接口正常返回带`error`元数据的失败任务，通用前端请求函数却把该对象当作HTTP错误字符串化。

### Suggested Fix
取证阶段独立保存最终响应和元数据，使用低温、关闭思考的结构化重试；连续失败时保留内部事实并禁止无证据原因，不丢弃已完成检查点。轮询任务状态时允许读取`error`元数据，并明确提取其`message`。

### Metadata
- Reproducible: yes
- Related Files: utils/monthly_report_narrative.py, assets/strategy-analysis.js, tests/test_monthly_narrative_pipeline.py
- Pattern-Key: harden.optional_enrichment_failure_boundary

### Resolution
- **Resolved**: 2026-10-01T23:20:00+08:00
- **Notes**: 增加取证三次重试、独立诊断留存和仅内部事实的安全降级；修复前端结构化错误解析。20项自动测试通过，并从原run_id恢复，跨过原故障点完成四批主旨句及概述页，任务状态达到100%。

---

## [ERR-20260929-003] market_mcp_config_launcher_closed

**Logged**: 2026-09-29T12:20:00+08:00
**Priority**: medium
**Status**: resolved
**Area**: config

### Summary
双击四个 MCP 插件配置启动器后，控制台窗口立即关闭，用户无法看到 Token 提示或启动错误。

### Error
```text
配置四个MCP插件.cmd 窗口启动后立即消失
```

### Context
- Windows Explorer 双击启动 `.cmd`。
- 原启动器依赖批处理末尾的 `pause`，启动阶段错误仍可能让瞬时窗口不可诊断。

### Suggested Fix
使用 PowerShell `-NoExit` 保持诊断窗口，配置脚本捕获错误并写入不包含 Token 的日志。

### Metadata
- Reproducible: unknown
- Related Files: 配置四个MCP插件.cmd, scripts/configure_market_mcp.ps1

### Resolution
- **Resolved**: 2026-09-29T12:20:00+08:00
- **Notes**: 启动器改为 `-NoExit`，并增加安全错误提示与诊断日志。

---
## [ERR-20261001-001] Restricted token hid existing TCP listeners from Get-NetTCPConnection

**Logged**: 2026-10-01
**Priority**: high
**Status**: resolved
**Area**: deployment

### Summary
The restart scripts used `Get-NetTCPConnection`, which returned no usable listener data under a restricted Windows token. Repeated restarts therefore left three Python processes listening on port 7860 and could serve stale code.

### Resolution
- **Resolved**: 2026-10-01
- **Notes**: Replaced listener discovery in both restart scripts with `netstat -ano` parsing, verified every target PID is Python before stopping it, and confirmed exactly one listener remains on ports 7860 and 8820.

---
## [ERR-20260930-006] PowerShell smoke test reused the reserved HOME variable

**Logged**: 2026-09-30
**Priority**: low
**Status**: resolved
**Area**: tests

### Summary
A local HTTP smoke test assigned its response to `$home`, but PowerShell variable names are case-insensitive and `$HOME` is read-only.

### Resolution
- **Resolved**: 2026-09-30
- **Notes**: Renamed the task-specific variable to `$rootResponse` and reran the check successfully.

---

## [ERR-20260930-002] brittle_skill_text_assertion

**Logged**: 2026-09-30T00:00:00+08:00
**Priority**: low
**Status**: resolved
**Area**: tests

### Summary
A smoke test asserted one exact Chinese phrase instead of the skill's behavioral invariant.

### Error
```
AssertionError
```

### Context
- The corrected skill used equivalent wording in English and Chinese.
- The macro route itself loaded successfully.

### Suggested Fix
Assert the route ID and stable instruction headings/requirements, not generated or translated prose.

### Metadata
- Reproducible: yes
- Related Files: skills/macro-monthly-report/SKILL.md, app.py

### Resolution
- **Resolved**: 2026-09-30T00:00:00+08:00
- **Notes**: Replaced the exact-phrase check with invariant checks.

---

## [ERR-20260930-001] skill_validator_windows_encoding

**Logged**: 2026-09-30T00:00:00+08:00
**Priority**: low
**Status**: resolved
**Area**: tests

### Summary
The skill validator used the Windows default GBK codec and could not read the UTF-8 Chinese SKILL.md.

### Error
```
UnicodeDecodeError: 'gbk' codec can't decode byte ...
```

### Context
- `quick_validate.py` calls `Path.read_text()` without an explicit encoding.
- The macro monthly skill is correctly stored as UTF-8.

### Suggested Fix
Run the validator with `PYTHONUTF8=1` on Windows.

### Metadata
- Reproducible: yes
- Related Files: skills/macro-monthly-report/SKILL.md

### Resolution
- **Resolved**: 2026-09-30T00:00:00+08:00
- **Notes**: Re-ran the official validator in UTF-8 mode.

---

## [ERR-20260929-007] playwright_mcp_browser_initialization_timeout

**Logged**: 2026-09-29T23:05:00+08:00
**Priority**: high
**Status**: resolved
**Area**: backend

### Summary
AgentScope 2.0.3 connected to Playwright MCP and listed tools, but every first browser tool call waited until timeout because the Chrome process crashed during initialization.

### Error
```
McpError: Timed out while waiting for response to ClientRequest.
browser_tabs -> Chrome GPU process exited unexpectedly -> browser process exit
EPERM: operation not permitted, open '%LOCALAPPDATA%\\ms-playwright\\b\\browser@...'
```

### Context
- Windows, AgentScope 2.0.3, MCP Python SDK 1.27.2.
- `@playwright/mcp` is pinned to 0.0.82 and uses Playwright 1.64 alpha.
- Installed Chrome is 137.0.7151.120.
- Both stdio and Streamable HTTP connected and listed tools normally; both stalled at `browser_tabs` before the fix.
- No `--cdp-endpoint` was configured.
- Debug logs showed the Chrome GPU process repeatedly crashing and the browser exiting with an access violation. After adding `--no-sandbox`, Playwright reached its browser registry but could not write below the default Local AppData directory.

### Suggested Fix
On this managed Windows host, launch Playwright MCP with `--no-sandbox`, redirect the subprocess `LOCALAPPDATA` to a writable project runtime directory, and pass the active local proxy explicitly when required. Keep every diagnostic stage bounded and inspect browser-server stderr instead of extending tool timeouts.

### Metadata
- Reproducible: yes
- Related Files: tools/monthly_report_browser.py, scripts/probe_playwright_mcp.py, scripts/playwright_mcp_probe_config.json
- See Also: ERR-20260928-008

### Resolution
- **Resolved**: 2026-09-29T23:05:00+08:00
- **Notes**: Streamable HTTP, stdio with the pinned local CLI, and stdio through Windows `npx.cmd` all completed connect, list_tools, browser_tabs, browser_navigate(https://example.com), and browser_snapshot. The direct local Playwright driver remains the default fallback.

---

## [ERR-20260929-006] skill_validator_windows_encoding

**Logged**: 2026-09-29T16:15:00+08:00
**Priority**: low
**Status**: resolved
**Area**: tests

### Summary
The bundled skill validator used the Windows default GBK codec and failed to read a UTF-8 Chinese `SKILL.md`.

### Error
```
UnicodeDecodeError: 'gbk' codec can't decode byte ...
```

### Context
- The target skill is UTF-8 and contains Chinese instructions.
- Python syntax and the narrative evidence validator had already passed.

### Suggested Fix
Run the bundled validator with Python UTF-8 mode (`-X utf8`) on Windows.

### Metadata
- Reproducible: yes
- Related Files: passenger-car-monthly-report/SKILL.md, skill-creator/scripts/quick_validate.py

### Resolution
- **Resolved**: 2026-09-29T16:15:00+08:00
- **Notes**: Re-ran the validator with `-X utf8`.

---

## [ERR-20260929-005] powershell_inline_if_expression

**Logged**: 2026-09-29T16:00:00+08:00
**Priority**: low
**Status**: resolved
**Area**: config

### Summary
An environment-presence check used `if` directly inside a parenthesized string expression, which Windows PowerShell parsed as a command name.

### Error
```
if: The term 'if' is not recognized as a name of a cmdlet, function, script file, or executable program.
```

### Context
- The command only checked whether Tavily and market-plugin environment variables were present.
- No secret value was printed and no project file was changed.

### Suggested Fix
Assign the status with a normal `if/else` statement before concatenating it into output.

### Metadata
- Reproducible: yes
- Related Files: model_config/config.json, tools/custom_tools.py

### Resolution
- **Resolved**: 2026-09-29T16:00:00+08:00
- **Notes**: Retried with a separate `$status` assignment and continued to expose presence only.

---

## 2026-07-16 - AgentScope Web 请求复用已关闭事件循环

- 症状：Web 服务连续请求 Agent 时出现 `RuntimeError: Event loop is closed`，工具调用和报告生成会中断。
- 原因：请求处理线程内对同一类异步 Agent 调用重复创建并关闭事件循环。
- 修复：在 `app.py` 中由 `AgentEventLoopRunner` 维护一个常驻事件循环，并使用线程安全提交方式串行执行 Agent 请求。
- 预防：新增需要连续 Web 调用的异步能力时，复用该运行器，不要在请求处理函数中直接调用 `asyncio.run()`。

## 2026-07-16 - agent-reach 的 MCP 元数据未加载

- 症状：尝试通过 `mcporter call exa...` 查询 MiniMax 官方资料时提示 `Unable to load tool metadata; name positional arguments explicitly.`。
- 原因：当前本地 agent-reach/MCP 工具元数据未正确加载，无法完成该次调用。
- 处理：改用官方 MiniMax 文档页面进行最小必要核验；未依赖该失败调用产出的任何事实。
- 预防：后续需要该渠道时，先运行 agent-reach 的诊断命令并确认 MCP 工具元数据可用。

## 2026-07-17 - 月报 Skill 日志模板导致前端脚本整体失效

- 症状：点击任意“Skill / 工具链能力”按钮后，任务输入框没有自动填充内容。
- 原因：新增月报 Skill 的前端日志中，将 JavaScript 模板字符串错误写成 `\`` 和 `\${`；浏览器报 `SyntaxError: Invalid or unexpected token`，后续所有点击事件都没有绑定。
- 修复：精确还原 6 个模板反引号和 7 个插值标记，并用 Playwright 连续点击 7 个 Skill 按钮完成验证。
- 预防：新增内嵌 JavaScript 的模板字符串后，运行 `tests/test_web_skill_bindings.py`；该测试会拒绝危险的转义标记。

## 2026-07-17 - agent-browser 无法自动启动调试浏览器

- 症状：`agent-browser` 返回 `Auto-launch failed: CDP response channel closed`。
- 原因：本地 agent-browser 的 CDP 自动启动通道异常，与本项目 Web 页面无关。
- 处理：改用项目虚拟环境中的 Playwright 完成页面错误采集和真实点击回归。
- 预防：后续如需使用 agent-browser，先单独诊断其浏览器/CDP 安装状态；项目 UI 回归优先保留 Playwright 测试路径。

---

## [ERR-20260719-001] powerpoint-com-visibility

**Logged**: 2026-07-19
**Priority**: low
**Status**: resolved
**Area**: tests

### Summary
PowerPoint COM automation does not accept a PowerShell Boolean for the `Visible` property.

### Error
```
Cannot convert value "False" to type "Microsoft.Office.Core.MsoTriState".
```

### Context
- Operation: render a generated PPTX to temporary PNG files for visual QA.
- Environment: Windows PowerPoint COM automation.

### Suggested Fix
Do not set `Visible` for headless export, or use the Office `MsoTriState` numeric constant rather than `$false`.

### Metadata
- Reproducible: yes
- Related Files: outputs/ppt/2026年4月中国乘用车市场月报_20260719_115524.pptx

---

## [ERR-20260719-003] top-model-parser-helper

**Logged**: 2026-07-19
**Priority**: medium
**Status**: resolved
**Area**: tests

### Summary
The newly added TOP15 preview parser referenced a missing safe-cell helper.

### Error
```
NameError: name 'cell_value' is not defined
```

### Context
- Operation: monthly Skill regression tests after adding TOP15 table recognition.
- Impact: Skill preparation failed before model invocation; no service restart occurred.

### Suggested Fix
Define a bounds-safe `cell_value` helper in the runtime module and retain the regression test for TOP15 recognition.

### Metadata
- Reproducible: yes
- Related Files: skills/market_analysis_skill/runtime.py

---

## [ERR-20260719-002] slide-summary-boundary-test

**Logged**: 2026-07-19
**Priority**: low
**Status**: resolved
**Area**: tests

### Summary
The first version of PPT slide-summary truncation ignored a valid short first sentence and still returned a fragment.

### Error
```
Expected: 第一句已完整。
Actual: 第一句已完整。第二句很长但不能被截。
```

### Context
- Operation: unit test for natural sentence-boundary truncation.
- Root cause: the preferred boundary threshold rejected the only available complete sentence.

### Suggested Fix
Use the latest available sentence terminator within the character limit before considering comma or raw-length fallback.

### Metadata
- Reproducible: yes
- Related Files: utils/monthly_report_pptx.py, tests/test_monthly_report_pptx.py

---
## [ERR-20260929-002] optional_domain_audit_blocked_initializer

**Logged**: 2026-09-29T00:00:00+08:00
**Priority**: medium
**Status**: resolved
**Area**: backend

### Summary
Policy/rights initialization completed its transaction but the command exited with an error when an optional new-car audit queried a table the runtime database user could not read.

### Error
```
psycopg2.errors.InsufficientPrivilege: permission denied for table new_car_model
```

### Context
- The failure occurred after the policy/rights transaction completed.
- New-car and reputation tables have a different owner/privilege boundary.
- Optional cross-domain verification should not make the required import appear failed.

### Suggested Fix
Catch database permission errors per optional domain, report `select_permission_required`, and retain a successful exit for completed policy/rights imports.

### Metadata
- Reproducible: yes
- Related Files: mcp/scripts/initialize_database.py

### Resolution
- **Resolved**: 2026-09-29T00:00:00+08:00
- **Notes**: Domain audits are now isolated and return structured warnings without failing initialization.

---
## [ERR-20260929-001] foundation_sandbox_write_tool_unavailable

**Logged**: 2026-09-29T00:00:00+08:00
**Priority**: medium
**Status**: pending
**Area**: infra

### Summary
The requested direct import to the 192.168.3.146 internal database could not be executed from this session because Foundation Sandbox only permits read-only access and its MCP tools were not exposed.

### Error
```
No foundation_sandbox_mcp tools or resources were available in the active session.
```

### Context
- The user authorized importing non-database policy/rights data.
- Foundation Sandbox instructions prohibit arbitrary SQL and direct writes to the internal business database.
- Policy and rights import was therefore packaged as an explicit server-side initialization task rather than bypassing access controls.

### Suggested Fix
Expose an approved Foundation Sandbox ingestion tool, or run `scripts/initialize_database.py` on the target server using a controlled database account.

### Metadata
- Reproducible: yes
- Related Files: mcp/scripts/initialize_database.py, mcp/deploy/sql/001_market_mcp.sql

---
## [ERR-20260928-006] unrelated_monthly_report_regressions

**Logged**: 2026-09-28T00:00:00+08:00
**Priority**: medium
**Status**: pending
**Area**: tests

### Summary
The pre-existing monthly-report test suite has eight failures because its default dataset and matching research evidence are unavailable or changed.

### Error
```
Ran 30 tests: FAILED (failures=7, errors=1)
```

### Context
- All five new market MCP tests passed in the same run.
- Failing tests concern `dataset_path=None`, missing selected month/TOP15 data, missing R1-R6 evidence and related report gates.
- No MCP server or AgentScope MCP assertion failed.

### Suggested Fix
Restore or explicitly configure the monthly-report fixture dataset and matching evidence pack, then address that suite in a separate task.

### Metadata
- Reproducible: yes
- Related Files: tests/test_market_analysis_skill.py, skills/market_analysis_skill/runtime.py

---
## [ERR-20260928-005] python_dash_c_async_def_syntax

**Logged**: 2026-09-28T00:00:00+08:00
**Priority**: low
**Status**: resolved
**Area**: tests

### Summary
A multi-line asynchronous MCP smoke test was incorrectly compressed into `python -c` after a semicolon.

### Error
```
SyntaxError: invalid syntax
```

### Context
- The Streamable HTTP policy server had started successfully on port 18811.
- Python compound statements such as `async def` cannot follow a semicolon in this form.

### Suggested Fix
Use a checked-in Python smoke-test script for asynchronous MCP client probes.

### Metadata
- Reproducible: yes
- Related Files: mcp/scripts/smoke_market_mcp_http.py

### Resolution
- **Resolved**: 2026-09-28T00:00:00+08:00
- **Notes**: Added and used a reusable asynchronous HTTP smoke-test script.

---
## [ERR-20260928-004] docker_cli_unavailable_for_compose_validation

**Logged**: 2026-09-28T00:00:00+08:00
**Priority**: low
**Status**: resolved
**Area**: infra

### Summary
The local Windows workspace does not have the Docker CLI, so Compose could not be validated with `docker compose config`.

### Error
```
The term 'docker' is not recognized as a name of a cmdlet, function, script file, or executable program.
```

### Context
- The four MCP services are intended for deployment on `192.168.3.146`, not on this workstation.
- Python compilation and MCP tool tests had already passed.

### Suggested Fix
Parse the Compose YAML locally for structural errors and run `docker compose config` plus container smoke tests on the target server during deployment.

### Metadata
- Reproducible: yes
- Related Files: mcp/deploy/docker-compose.yml

### Resolution
- **Resolved**: 2026-09-28T00:00:00+08:00
- **Notes**: Used the available YAML parser for local structural validation; retained target-server Compose validation in the deployment checklist.

---
## [ERR-20260928-003] pytest_not_installed_in_workspace

**Logged**: 2026-09-28T00:00:00+08:00
**Priority**: low
**Status**: resolved
**Area**: tests

### Summary
The workspace Python runtime does not include pytest, so the new MCP smoke tests could not start with `python -m pytest`.

### Error
```
E:\AI\data\envs\helloagent\Scripts\python.exe: No module named pytest
```

### Context
- Attempted to run `tests/test_market_data_mcp.py` after adding four MCP servers.
- The application dependencies do not declare pytest.

### Suggested Fix
Use the standard-library `unittest` runner for project smoke tests unless pytest is explicitly added as a development dependency.

### Metadata
- Reproducible: yes
- Related Files: tests/test_market_data_mcp.py

### Resolution
- **Resolved**: 2026-09-28T00:00:00+08:00
- **Notes**: Converted the MCP test module to `unittest` and used `python -m unittest`.

---
## [ERR-20260928-003] pytest_not_installed_in_workspace_runtime

**Logged**: 2026-09-28T00:00:00+08:00
**Priority**: low
**Status**: pending
**Area**: tests

### Summary
The workspace virtual environment can run the application but does not include pytest.

### Error
```
E:\AI\data\envs\helloagent\Scripts\python.exe: No module named pytest
```

### Context
- Attempted to run `tests/test_web_skill_bindings.py` after adding the forecast Skill integration.
- Python syntax checks, JavaScript syntax checks, Skill loading, desktop UI, mobile UI, and a live forecast request were verified independently.

### Suggested Fix
Add pytest to the development dependency set when automated test execution is required; do not install it implicitly during product work.

### Metadata
- Reproducible: yes
- Related Files: tests/test_web_skill_bindings.py, requirements.txt

---

## [ERR-20260928-003] port_listener_parser

**Logged**: 2026-09-28T17:30:00+08:00
**Priority**: low
**Status**: resolved
**Area**: infra

### Summary
The first 7860 restart check parsed `netstat` rows as nested arrays and then treated TIME_WAIT rows as a remaining listener.

### Error
```
No listener on 7860
Port 7860 is still occupied after stop.
```

### Context
- The service did have one LISTENING row and several TIME_WAIT rows.
- The array indexing logic did not reliably extract the LISTENING PID.

### Suggested Fix
Match the complete LISTENING row with an anchored regular expression and extract only its final PID field.

### Metadata
- Reproducible: yes
- Related Files: myproject/scripts/start_agent.ps1

### Resolution
- **Resolved**: 2026-09-28T17:31:00+08:00
- **Notes**: Replaced the ad-hoc row parsing with an anchored LISTENING-row match for the restart operation.

---
## [ERR-20260928-004] bundled_markitdown_unavailable

**Logged**: 2026-09-28T00:00:00+08:00
**Priority**: low
**Status**: resolved
**Area**: tests

### Summary
The bundled workspace Python did not include the `markitdown` module needed by the generic PPTX text-extraction command.

### Error
```
No module named markitdown
```

### Context
- Attempted read-only extraction of the supplied macro-economic monthly report template.
- No package installation was necessary because the project environment already provides `python-pptx`.

### Suggested Fix
Use `python-pptx` for structural and text inspection when `markitdown` is unavailable, or use the presentation runtime for rendering when visual inspection is needed.

### Metadata
- Reproducible: yes
- Related Files: none

### Resolution
- **Resolved**: 2026-09-28T00:00:00+08:00
- **Notes**: Switched to the existing project Python environment and read the template without modifying it.

---
## [ERR-20260928-003] project_update_route_indentation

**Logged**: 2026-09-28T00:00:00+08:00
**Priority**: low
**Status**: resolved
**Area**: backend

### Summary
The new project-quality update route was inserted with one extra indentation level.

### Error
```
IndentationError: expected an indented block (app.py, line 388)
```

### Context
- Detected immediately by `python -m py_compile app.py`.
- The route allow-list line under `do_POST` was over-indented.

### Suggested Fix
Keep route allow-list indentation aligned with the existing `do_POST` body and always run syntax validation after endpoint edits.

### Metadata
- Reproducible: yes
- Related Files: app.py

### Resolution
- **Resolved**: 2026-09-28T00:00:00+08:00
- **Notes**: Corrected indentation and reran validation.

---

## [ERR-20260928-003] agent_reach_jina_timeout

**Logged**: 2026-09-28T00:00:00+08:00
**Priority**: low
**Status**: resolved
**Area**: frontend

### Summary
Jina Reader could not reach the supplied AutoHome model page from this environment.

### Error
```
curl: (28) Failed to connect to r.jina.ai port 443 after 21083 ms
```

### Context
- Attempted to inspect `https://www.autohome.com.cn/7727/` through the agent-reach web route.
- The user had already supplied a screenshot containing the required vehicle image.

### Suggested Fix
When the authoritative page is unreachable but a user-provided screenshot contains the requested visual, use the screenshot as the edit target and clearly preserve the subject identity.

### Metadata
- Reproducible: unknown
- Related Files: assets/newcar/li-auto-i8-cutout.png

### Resolution
- **Resolved**: 2026-09-28T00:00:00+08:00
- **Notes**: Extracted a clean transparent vehicle cutout from the supplied screenshot and validated it in the detail hero.

---
## [ERR-20260928-001] start_agent_port_handoff_race

**Logged**: 2026-09-28T00:00:00+08:00
**Priority**: low
**Status**: resolved
**Area**: infra

### Summary
The restart helper saw port 7860 reoccupied by another Python instance between its stop and verification checks.

### Error
```
Port 7860 is still occupied by PID=28080.
```

### Context
- `scripts/start_agent.ps1` stopped the original listener, then a supervised project process relaunched `myproject/app.py` with another environment Python.
- Read-only process inspection confirmed that the replacement listener ran the same application.

### Suggested Fix
When this recurs, inspect the replacement listener command line before stopping anything; if it is the same app, verify the updated route rather than force another restart.

### Metadata
- Reproducible: unknown
- Related Files: scripts/start_agent.ps1, app.py

### Resolution
- **Resolved**: 2026-09-28T00:00:00+08:00
- **Notes**: `/api/projects` returned HTTP 200 and the served home page contained the new project registry.

---
## [ERR-20260928-002] powershell_reserved_home_variable

**Logged**: 2026-09-28T00:00:00+08:00
**Priority**: low
**Status**: resolved
**Area**: tests

### Summary
A PowerShell smoke check attempted to assign to `$home`, which is the case-insensitive built-in `$HOME` constant.

### Error
```
Cannot overwrite variable HOME because it is read-only or constant.
```

### Context
- The HTTP verification script used `$home=Invoke-WebRequest ...`.
- PowerShell variable names are case-insensitive.

### Suggested Fix
Use task-specific variable names such as `$taskPage` and `$projectResponse`.

### Metadata
- Reproducible: yes
- Related Files: none

### Resolution
- **Resolved**: 2026-09-28T00:00:00+08:00
- **Notes**: Re-ran the verification with task-specific variable names; both routes returned HTTP 200.

---

## [ERR-20260928-005] intelligence_detail_export_validation

**Logged**: 2026-09-28T06:10:00+08:00
**Priority**: low
**Status**: resolved
**Area**: tests

### Summary
Detail-page QA exposed a hidden-checkbox automation mismatch and an exact template-header spelling difference.

### Error
```
TimeoutError: visible activity-type label intercepted the hidden checkbox click
ValueError: 地方促消费政策展示表头已变化，请先更新字段映射
```

### Context
- Rights activity filters use visually styled labels over accessible checkbox inputs.
- The supplied policy template spells column 12 as `促消费类型（统一表准/不统一标准）`; exact export alignment must preserve that source spelling.

### Suggested Fix
Exercise styled checkboxes through their visible labels and treat the template workbook's cell text as the authoritative export header.

### Metadata
- Reproducible: yes
- Related Files: home.html, assets/home.js, scripts/build_intelligence_snapshot.py, app.py

### Resolution
- **Resolved**: 2026-09-28T06:14:00+08:00
- **Notes**: Updated the UI automation to click the label, enforced template-header equality during snapshot generation, and validated 18 policy plus 21 rights columns character-for-character.

---

## [ERR-20260928-003] spreadsheet_skill_path_and_lock_file

**Logged**: 2026-09-28T05:20:00+08:00
**Priority**: low
**Status**: resolved
**Area**: config

### Summary
The initial spreadsheet inspection used an obsolete skill path and included Excel's temporary lock workbook.

### Error
```
Cannot find path '...dependencies\skills\spreadsheets\SKILL.md'
PermissionError: [Errno 13] Permission denied: '~$地方政策+权益表头.xlsx'
```

### Context
- The installed spreadsheet skill lives under the versioned Codex plugin cache.
- The source folder contained an open-workbook lock file beginning with `~$`.

### Suggested Fix
Resolve the skill path from the active skills catalog and exclude `~$*.xlsx` files from workbook discovery.

### Metadata
- Reproducible: yes
- Related Files: scripts/build_intelligence_snapshot.py

### Resolution
- **Resolved**: 2026-09-28T05:21:00+08:00
- **Notes**: Read the versioned skill file and restricted processing to the three named source workbooks.

---

## [ERR-20260928-004] visual_qa_preview_entrypoint

**Logged**: 2026-09-28T05:35:00+08:00
**Priority**: low
**Status**: resolved
**Area**: tests

### Summary
The first visual QA request opened a stale service and then the static server directory listing instead of the updated homepage.

### Error
```
TimeoutError: waiting for locator("#policy-total")
TimeoutError: waiting for locator("#intelligence-title")
```

### Context
- Port 7860 returned an already-running older homepage snapshot.
- Python's static server served a directory listing at `/` because the project entry file is `home.html`, not `index.html`.

### Suggested Fix
Use an isolated preview port and open `/home.html` explicitly for this project.

### Metadata
- Reproducible: yes
- Related Files: home.html, assets/home.css, assets/home.js

### Resolution
- **Resolved**: 2026-09-28T05:36:00+08:00
- **Notes**: Re-ran desktop and mobile Playwright checks against the isolated `/home.html` preview; both passed.

---
## [ERR-20260928-001] powershell_inline_python_sql_quoting

**Logged**: 2026-09-28T00:00:00+08:00
**Priority**: low
**Status**: resolved
**Area**: backend

### Summary
A nested PowerShell `python -c` verification command failed while parsing SQL punctuation.

### Error
```
ParserError: Missing argument in parameter list.
```

### Context
- A Python one-liner embedded SQL, list comprehensions, and nested quotes inside a PowerShell command string.
- The database import had already succeeded; only the read-only verification command failed.

### Suggested Fix
Use a small temporary `.py` helper for multi-line database verification rather than nesting Python and SQL inside PowerShell quoting.

### Metadata
- Reproducible: yes
- Related Files: myproject/tools/new_car_detail_sync.py
- See Also: earlier inline Python/SQL quoting error in this file
- Recurrence-Count: 2
- Last-Seen: 2026-09-28

### Resolution
- **Resolved**: 2026-09-28T00:00:00+08:00
- **Notes**: Switched verification to a temporary Python helper. Recurred once while combining MCP tool-count and PowerShell checks; subsequent checks were split into simple commands.

---
## [ERR-20260927-001] agent_reach_exa_network_denied

**Logged**: 2026-09-27T00:00:00+08:00
**Priority**: low
**Status**: resolved
**Area**: infra

### Summary
Agent Reach's Exa search backend could not connect from the managed workspace network.

### Error
```
SSE error: TypeError: fetch failed: connect EACCES 104.18.6.160:443
```

### Context
- Attempted an Exa web search for 2018 Chinese passenger-car monthly sales and NEV data.
- The managed PowerShell process was denied outbound access before any result was returned.

### Suggested Fix
Use the built-in read-only web search fallback when Agent Reach reports an EACCES connection failure in this environment.

### Metadata
- Reproducible: unknown
- Related Files: none

### Resolution
- **Resolved**: 2026-09-27T00:00:00+08:00
- **Notes**: Continued with the built-in web search fallback; no business code was changed for this integration issue.

---

## [ERR-20260921-001] planning-workbook-analysis-runtime

**Logged**: 2026-09-21T00:00:00+08:00
**Priority**: low
**Status**: resolved
**Area**: backend

### Summary
The project virtual environment does not include pandas for ad-hoc workbook statistics.

### Error
```
ModuleNotFoundError: No module named 'pandas'
```

### Context
- Operation: inspect the planning-new-car workbook before importing it into the web application.
- Environment: `E:\AI\data\envs\helloagent\Scripts\python.exe`.

### Suggested Fix
Use the bundled workspace Python runtime for pandas analysis, or use the already-installed openpyxl package when only workbook inspection is required. Do not install another dependency for this task.

### Metadata
- Reproducible: yes
- Related Files: tools/new_car_sync.py, new-car-detail.html

### Resolution
- **Resolved**: 2026-09-21T00:00:00+08:00
- **Notes**: Switched workbook statistics to the bundled workspace runtime without changing the source workbook.

---
## [ERR-20260921-002] parallel_powershell_skill_reads

**Logged**: 2026-09-21T00:00:00+08:00
**Priority**: medium
**Status**: resolved
**Area**: infra

### Summary
Parallel PowerShell processes failed while reading two skill files during the口碑 POC task.

### Error
```
Fatal error: Releasing the double mapped memory failed
PowerShell configuration read failed with OutOfMemoryException
```

### Context
- Three PowerShell commands were launched concurrently to read local files.
- The spreadsheet files themselves were not implicated.

### Suggested Fix
Read large local instruction files sequentially with `cmd.exe /c type` in this Windows runtime.

### Metadata
- Reproducible: unknown
- Related Files: C:/Users/11489/.codex/skills/xlsx/SKILL.md, C:/Users/11489/.codex/skills/frontend-polish/SKILL.md

### Resolution
- **Resolved**: 2026-09-21T00:00:00+08:00
- **Notes**: Sequential `cmd.exe` reads succeeded.

---
## [ERR-20260921-003] windows_python_command_quoting

**Logged**: 2026-09-21T20:00:00+08:00
**Priority**: low
**Status**: resolved
**Area**: infra

### Summary
Two ad-hoc Windows Python invocations failed because nested shell quoting corrupted the executable or inline SQL string.

### Error
```
The quoted Python executable was not recognized by cmd.exe.
SyntaxError: '(' was never closed
```

### Context
- A quoted absolute executable was passed through `cmd.exe`.
- A long `python -c` expression contained nested PowerShell, Python, and SQL quoting.

### Suggested Fix
Use PowerShell's call operator for quoted executable paths and use a short checked-in `.py` helper for multi-line queries.

### Metadata
- Reproducible: yes
- Related Files: myproject/.work/verify_reputation_poc.py

### Resolution
- **Resolved**: 2026-09-21T20:00:00+08:00
- **Notes**: Both operations succeeded using the safer forms above.

---
## [ERR-20260924-001] startup_script_path_mismatch

**Logged**: 2026-09-24T00:00:00+08:00
**Priority**: low
**Status**: resolved
**Area**: config

### Summary
The pasted startup target differed from the actual desktop launcher target.

### Error
```
Cannot find path 'E:\AI\data\envs\helloagent\myproject\start\_agent.cmd'
```

### Context
- The provided snippet referenced `start\_agent.cmd`.
- The real desktop file calls `myproject\start_agent.cmd`.

### Suggested Fix
Inspect the launcher file on disk before editing nested startup scripts.

### Metadata
- Reproducible: yes
- Related Files: C:/Users/11489/Desktop/AI智能体.cmd, myproject/start_agent.cmd

### Resolution
- **Resolved**: 2026-09-24T00:00:00+08:00
- **Notes**: Updated the actual called script.

---
## [ERR-20260927-002] preview_used_system_python

**Logged**: 2026-09-27T00:00:00+08:00
**Priority**: low
**Status**: resolved
**Area**: config

### Summary
The first local preview launch used the system Python instead of the workspace virtual environment.

### Error
```
ModuleNotFoundError: No module named 'agentscope'
```

### Context
- `python app.py` resolved to `C:\Program Files\Python39\python.exe` in the login shell.
- The project runtime is `E:\AI\data\envs\helloagent\Scripts\python.exe`, as documented by `scripts/start_agent.ps1`.

### Suggested Fix
Use the project's existing start script or the explicit workspace Python when previewing this application.

### Metadata
- Reproducible: yes
- Related Files: scripts/start_agent.ps1, app.py
- Recurrence-Count: 3
- Last-Seen: 2026-09-28

### Resolution
- **Resolved**: 2026-09-27T00:00:00+08:00
- **Notes**: Continued validation with the explicit workspace Python. Recurred on 2026-09-28 during project-archive and macro-ledger smoke tests; use `E:\AI\data\envs\helloagent\Scripts\python.exe` for all app imports.

---
## [ERR-20260929-003] windows_powershell_parser_probe_quoting

**Logged**: 2026-09-29T12:00:00+08:00
**Priority**: low
**Status**: resolved
**Area**: tests

### Summary
A Windows PowerShell 5.1 syntax-probe command lost its variable name because the outer PowerShell expanded it before invoking the child process.

### Error
```
= : The term '=' is not recognized
[ref] cannot be applied to a variable that does not exist
```

### Context
- The target script had already been converted to UTF-8 with BOM.
- Only the nested validation command was malformed; the target file was unaffected.

### Suggested Fix
Avoid variables in nested `-Command` probes; parse the target text directly with `[scriptblock]::Create(...)`.

### Metadata
- Reproducible: yes
- Related Files: scripts/configure_market_mcp.ps1

### Resolution
- **Resolved**: 2026-09-29T12:00:00+08:00
- **Notes**: Replaced the nested variable-based probe with a direct parser invocation.

---
## [ERR-20260929-004] plugin_retry_patch_context

**Logged**: 2026-09-29T14:00:00+08:00
**Priority**: low
**Status**: resolved
**Area**: frontend

### Summary
The first plugin-status retry patch used stale context from an earlier read of `home.js`.

### Error
```
apply_patch verification failed: Failed to find expected lines
```

### Context
- The live file used `is-connected` and no longer pre-activated all plugin cards.
- No file content was changed by the failed patch.

### Suggested Fix
Read the smallest current line window immediately before patching frequently edited frontend files.

### Metadata
- Reproducible: yes
- Related Files: assets/home.js

### Resolution
- **Resolved**: 2026-09-29T14:00:00+08:00
- **Notes**: Re-read the exact block and applied the retry/cache patch with current context.

---
## [ERR-20260930-001] stale_in_memory_home_html

**Logged**: 2026-09-30T00:00:00+08:00
**Priority**: low
**Status**: resolved
**Area**: tests

### Summary
HTTP validation initially saw removed homepage content because two Python processes were simultaneously listening on port 7860 and one retained startup-cached HTML.

### Error
```
Served page still contains: 实时运行统计
```

### Context
- The saved HTML and JavaScript changes were valid.
- `app.py` loads `home.html` into a module-level `HTML` variable at startup.
- Two Python listeners shared port 7860, so requests could still reach the older process after a new instance started.

### Suggested Fix
Verify the exact listener count, stop all validated project Python listeners on port 7860, then start one instance before validating served HTML.

### Metadata
- Reproducible: yes
- Related Files: app.py, home.html, scripts/start_agent.ps1

### Resolution
- **Resolved**: 2026-09-30T00:00:00+08:00
- **Notes**: Stopped both verified Python listeners, started one fresh instance, and confirmed only one listener remained and the live page no longer contained the removed sections.

---
## [ERR-20260930-003] Unit tests were launched with the system Python

**Logged**: 2026-09-30
**Status**: resolved

### What happened
Targeted web binding tests failed during import because the default `python` executable did not include the project's `agentscope` dependency.

### Resolution
Run project tests through the virtual-environment launcher used by the 7860 startup script: `E:\AI\data\envs\helloagent\Scripts\python.exe`. Calling the base interpreter shown in process metadata bypasses the environment's compatibility shims.

### Prevention
Before running project tests, read the startup script and use its declared Python launcher rather than the resolved base executable shown by process metadata.
## [ERR-20260930-004] Skill runtime timestamp depended on missing Windows tzdata

**Logged**: 2026-09-30
**Priority**: medium
**Status**: resolved
**Area**: backend

### Summary
New Skill runtime tests failed before execution because `ZoneInfo("Asia/Shanghai")` required a tzdata package not present in the project virtual environment.

### Error
`zoneinfo._common.ZoneInfoNotFoundError: No time zone found with key Asia/Shanghai`

### Suggested Fix
Use a fixed UTC+8 timezone for local run-state timestamps so the runtime does not depend on an optional timezone database.

### Resolution
- **Resolved**: 2026-09-30
- **Notes**: Replaced `ZoneInfo` with `timezone(timedelta(hours=8))`.

---
## [ERR-20260930-005] Inline smoke test used an invalid async function declaration

**Logged**: 2026-09-30
**Priority**: low
**Status**: resolved
**Area**: tests

### Summary
A one-line diagnostic placed `async def` after semicolon-separated statements, which is invalid Python syntax.

### Resolution
- **Resolved**: 2026-09-30
- **Notes**: Replaced the unnecessary async wrapper with a direct synchronous inventory call.

---
## [ERR-20261002-001] monthly_overview_retry_boundary

**Logged**: 2026-10-02T01:27:00+08:00
**Priority**: high
**Status**: resolved
**Area**: backend

### Summary
月报四个分批已完成后，概述页数字校验或模型连接错误会绕过局部重试并将整个后台任务标记失败。

### Error
```
RuntimeError: 概述页出现分页面结论之外的数字：['-19.6', '-26', '80']
APIConnectionError: Connection error.
```

### Context
- 运行编号：month-20261002-010557-694d49f5
- B1-B4 已持久化完成，失败仅发生在概述页。
- 数字来源校验原本位于概述重试循环之外；`agent.reply()` 也位于异常捕获之外。

### Suggested Fix
把模型调用、JSON解析、结构校验和数字回溯校验统一纳入概述页局部重试；连续失败时仅复用已验收分页面结论生成确定性概述，不丢弃已完成批次。

### Metadata
- Reproducible: yes
- Related Files: utils/monthly_report_narrative.py
- See Also: ERR-20261001-002

### Resolution
- **Resolved**: 2026-10-02T01:27:00+08:00
- **Notes**: 已增加四次概述级重试、连接异常捕获及安全概述回退；所有模型请求纳入其所在批次的异常处理。

---

## [ERR-20261003-MCA] parallel_test_edit

**Logged**: 2026-10-03T09:59:24Z
**Priority**: low
**Status**: resolved
**Area**: tests

### Summary
并行协作时测试文件已被另一智能体调整，补丁的旧上下文匹配失败。

### Error
`apply_patch verification failed: Failed to find expected lines`。

### Context
- 宏观月报新增经济一致性门禁后，修订合成数据验收断言。
- 同一断言在读取与补丁之间被同步修改；文件内容完整，无数据损失。

### Suggested Fix
补丁失败时重新读取现状并通知协作者，仅增量修改；不要强制覆盖。回归输出使用隔离目录，保留已完成可视验收的固定文件。

### Metadata
- Reproducible: no
- Related Files: tests/test_macro_report_semantics.py

### Resolution
- **Resolved**: 2026-10-03T09:59:24Z
- **Notes**: 已重新读取并按新上下文追加严格断言，未覆盖其他修改。

---

## [ERR-20261003-002] unittest_selector

**Logged**: 2026-10-03T18:05:00+08:00
**Priority**: low
**Status**: resolved
**Area**: tests

### Summary
单项回归误用了不存在的测试类名，诊断命令未执行目标测试。

### Error
`AttributeError: module tests.test_macro_report_semantics has no attribute NativeMacroArtifactTest`。

### Suggested Fix
运行单项测试前从现有测试文件核对类名与方法名；此例正确类名为 `FullNativeChartUpdateTest`。使用隔离输出目录，不覆盖已验收的固定诊断稿。

### Metadata
- Reproducible: yes
- Related Files: tests/test_macro_report_semantics.py

### Resolution
- **Notes**: 已核对真实类名并由独立审计分支运行正确的精选回归；本次失败只涉及测试选择器，没有更改业务数据。

---

## [ERR-20261005-001] powershell_diagnostic_selection

**Logged**: 2026-10-05T21:03:11+08:00
**Priority**: low
**Status**: resolved
**Area**: tests

### Summary
Windows诊断中，传给rg的文件通配符被当作字面路径；受限令牌也不能读取Win32_Process。

### Error
`The filename, directory name, or volume label syntax is incorrect (os error 123)`；`Get-CimInstance: Access is denied`。服务响应头是多值集合，第一次身份检查因此安全阻止重载，未停止进程。

### Suggested Fix
文件过滤使用rg的`-g`参数而不是未展开路径。已有诊断进程完成时无需扩大权限读取全机进程信息；使用目标工具返回的进程状态。HTTP响应头先合并为字符串再校验，不能直接把多值集合当作单个字符串。

### Metadata
- Reproducible: yes
- Related Files: tests/test_macro_source_reuse.py

### Resolution
- 已改用目录加`-g`过滤；真实证据回放正常完成，未改动业务数据或扩大权限。

---

## [ERR-20261007-001] legacy_passenger_ppt_test_fixtures

**Logged**: 2026-10-07
**Priority**: medium
**Status**: pending
**Area**: tests

### Summary
修复新建分析入口的回归中，发现两项旧乘用车PPT测试仍假定数据包通过就可交付、无run_id也可导出模板，已不符合现有后台接口。

### Error
`test_ready_new_monthly_route_enables_ppt_export`: 实际为“等待主旨句门禁”，夹具期望“通过”。
`test_export_releases_verified_compatible_template`: `RuntimeError: 未找到对应的月报任务，请重新执行月报分析。`

### Context
本次只改主页与分析页的前端新建/恢复入口及对应UI测试，没有修改后端来源、主旨句或PPT交付门禁。其余13项绑定检查通过，7项针对性UI测试及实际浏览器空状态检查通过。用户正在跑的任务未重启、未删除。

### Suggested Fix
单独把旧夹具升级为持有run_id、完整主旨句验证和已验收PPT产物的隔离测试。不能为了通过旧测试放宽真实交付门禁。

### Metadata
- Reproducible: yes
- Related Files: tests/test_web_skill_bindings.py

---
## [ERR-20261012-NCM] new-car verification command boundaries

**Logged**: 2026-10-12T19:00:00+08:00
**Priority**: low
**Status**: resolved
**Area**: tests

### Summary
Windows verification needed explicit project import root and reliable browser fault injection.

### Error
`ModuleNotFoundError: integrations` when unittest discovery started from the environment root; an inline Python command used a literal backslash-n and failed syntax parsing; one patch started mid-HTML-line and failed context verification. Browser CLI route-abort did not prove the intended failure state.

### Suggested Fix
Give standalone tests an explicit project path; use valid one-line commands or saved tests; patch complete lines. Confirm the actual DOM state before accepting browser fault simulation.

### Metadata
- Reproducible: yes
- Related Files: tests/test_new_car_live.py, integrations/new_car_live.py

### Resolution
- Fixed test root and verified browser/HTTP outputs; no failed command changed business data.

---

## [ERR-20261013-REP] reputation verification harness

**Logged**: 2026-10-13T01:45:00+08:00
**Priority**: low
**Status**: resolved
**Area**: tests

### Summary
Inline Python/Powershell quoting and an unnecessary mock __class__ assignment interrupted diagnostics, not business data operations.

### Error
Inline diagnostics reported Python syntax errors. One unit test failed with `TypeError: __class__ assignment only supported for mutable types`.

### Suggested Fix
Keep nontrivial diagnostic code in saved scripts. Use explicit cursor/connection test doubles rather than modifying SimpleNamespace classes. Do not reuse guessed process session IDs.

### Resolution
Saved audit scripts used masked connection identities, test double corrected, 6 reputation and 7 new-car tests passed, actual MCP and 7860 interfaces/browser verified. No database records or collector scripts were modified.

### Metadata
- Related Files: ops/audit_reputation_mcp.py, ops/inspect_reputation_collectors.py, tests/test_reputation_live.py
- Reproducible: yes

---


## [ERR-20261013-MACRO-OFFICE] Reference preview startup

- Context: macro historical deck study; Python COM DispatchEx PowerPoint.Application.
- Observed: sandbox returned COM -2147023584 (logon session unavailable); isolated elevated attempt stalled before any preview artifact.
- Response: stopped only the verified Python preview process IDs; did not terminate Office or user browser processes.
- Lesson: verify actual rendered files; OOXML extraction is content evidence, never visual acceptance. Prefer existing reviewed Office-session runner for later delivery checks.
