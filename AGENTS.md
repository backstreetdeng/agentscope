# Project execution rules

## 统一规则入口

- 全项目开发规则以本文件为准；Codex 和 TRAE 平等执行 V2.0 轮班接力。开工先看 [任务清单](forecast-engine/share-files/TASKS.md) 和 [交接摘要](forecast-engine/share-files/HANDOFF.md)，只按当前工作需要查看源码及历史证据。
- 项目实际根为当前 checkout 的 myproject 仓库根。Codex 桌面项目可将其设为 Primary；从父工作空间启动时按父 AGENTS.md 路由到本文件。文件不可见时明确报告，不能假称已读、已同步或已合并。
- 旧的 Codex / TRAE 专属文件仅作兼容入口或历史参考；职责、读写及验收以本文件 V2.0 为准，不执行与 V2.0 冲突的旧规则。

## Development code graph and change verification

- For structural code exploration, use the installed `codebase-memory` skill. The graph project is `market-agent-web`, rooted only at `E:/AI/data/envs/helloagent/myproject`; never index the parent Python environment or migration materials.
- Follow [docs/codebase-memory-workflow.md](docs/codebase-memory-workflow.md). Start with `list_projects` / `index_status`; refresh the index when relevant files are changed or coverage is stale. A ready index alone does not establish freshness.
- Before changing behavior, identify the target symbols, trace relevant callers and dependencies, check all evidence paths with `check_index_coverage`, and read material source. Read/grep any missing, partial, excluded, or uncertain coverage. Dynamic registration and frontend events require source checks.
- After changes, inspect the actual Git diff (including staged changes and relevant untracked files), use `detect_changes` with an explicit comparison baseline, and run the checks appropriate to the affected behavior. Report commands/results, known baseline failures, coverage gaps, and any tests not run. Do not represent unrelated existing edits as changes from the current task.
- Keep indexing exclusions in `.cbmignore`. Never index credentials, browser profiles, raw business data, generated reports, dependencies or backups. Do not export graph snapshots into Git by default.
- The wrapper `scripts/codebase_memory.ps1` provides development queries and fixed-root refresh. It is not registered as a business Agent tool. Do not add the graph as a production request dependency or expose source access to ordinary business users.
- Static relationships and zero callers are evidence to investigate, not proof of runtime behavior, full impact, or dead code. Architecture decisions belong in versioned repository documents as well as any graph notes.

## Complete Skill integration

- Read and follow `docs/skill-integration-standard.md` before adding or changing a Skill integration.
- A Skill is an executable package, not injected `SKILL.md` text. The web agent must receive package-relative access to its manifest, references, assets, scripts, declared dependencies, tools, isolated run workspace, persistent task graph, checkpoints, and validators.
- Do not mark a Skill as integrated until a real representative task produces its required artifact and passes independent acceptance gates.
- Preserve capability parity: if Codex can execute a packaged asset or script that the web agent cannot access, the web integration is incomplete.
- Never claim completion from model prose alone. Completion comes from persisted task state, observable tool evidence, required artifacts, and passing validators.

## Provider credentials

- 用户当前指定默认 `deepseek-v4-flash`，复杂 Agent 任务使用 `deepseek-v4-pro`，禁止继续调用 MiniMax。模型选择遵循 `utils/model_routing.py`，不得擅自回退到未授权提供方。
- 当前 `.env` 中 `DASHSCOPE_API_KEY` 存放的是用户提供的 DeepSeek 凭证，只允许发送到已核实的 `api.deepseek.com`。这是历史变量名，不代表凭证仍属于阿里云；不输出、不复制或提交真实值。

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

## 根目录、文件落点与执行纪律

- 本项目根目录为 `E:/AI/data/envs/helloagent/myproject`。父目录是 Python 环境及其他项目所在位置，不得当作本项目根目录扫描、安装依赖或写入业务文件。
- 执行前确认工作目录、Git 状态和适用的 AGENTS.md；记录本任务改动边界，不覆盖、回退或顺带提交已有改动。
- 根目录仅保留入口、现有页面、依赖清单、项目说明及配置。新增脚本、截图、日志、备份和报告必须进入下表指定目录；现有入口迁移需先核对调用路径。
- 文件落点、清理分级和当前盘点见 [docs/directory-hygiene.md](docs/directory-hygiene.md)，后续任务开始前遵循此约定。
- Python 使用父环境的 `Scripts/python.exe`；执行命令显式指定工作目录，脚本根据自身位置解析项目根路径，禁止新增本机绝对路径。
- 常规启动使用 `start_agent.cmd` 或 `scripts/start_agent.ps1`；启动脚本可能重启服务，不作为整理文件时的验证手段。遵循上文月报浏览器保护规则。
- 一次性任务写入 `temp/<YYYYMMDD>-<task>/`；需复用的开发脚本放 `scripts/`，服务器发布/导入/修复放 `ops/`，测试放 `tests/`。脚本应说明输入、输出与副作用，默认不发布、不删除业务数据。
- 日志放 `logs/`，交付物放 `outputs/<task>/<run-id>/`，截图放同次输出的 `screenshots/`；运行状态和浏览器资料放 `runtime/`，稳定业务数据放 `data/`。不得仅因未被 Git 跟踪就视为垃圾。
- 用 Git 保存源码历史；确需文件备份时放 `backup/<YYYYMMDD>-<task>/`，附来源路径和恢复方法，不再在源文件旁生成 `.bak*`。
- 清理先列清单、核查引用与运行占用；归档使用显式路径、保留哈希清单且不覆盖目标。永久删除、业务数据/会话资料清理须获得针对该范围的明确授权。禁止直接执行 `git clean -fdx`、批量删除 runtime 或按文件年龄一刀切删除。
- 验证应与改动相称；目录整理核验清单、哈希和 Git 差异，行为变更再执行对应测试。交付时说明已整理项、保留项和待处理风险。
- 根目录白名单以 `docs/root-files.json` 为准。不得把单次任务的 `.log`、截图、脚本、报告、HTML 试稿或备份直接写入根目录；新增例外必须说明入口必要性并同步更新规则。
- 开始单次任务先确定 `task_id` 与输出位置。`outputs/`、`temp/`、`backup/` 的任务目录要写 `README.md` 或 `manifest.json`，记录用途、来源、重建命令、是否可清理和恢复方法；模板见 `docs/artifact-manifest-template.json`。未知用途文件标记待核实，不能靠后缀或日期删除。
- 新页面放 `pages/` 并接入路由；现有根目录页面按白名单保留，迁移必须同步修改调用方、测试和生成器。业务 Python 仍按现有模块分工，辅助脚本放 `scripts/`，不得将所有 `.py` 按扩展名混放。
- 每次任务交付前，从项目根目录执行 `../Scripts/python.exe -B scripts/workspace_hygiene.py`。发现新增根目录杂项时先归位；检查器只读，不会清理文件。引用与会话安全规则继续适用。

## Codex + TRAE 轮班接力 V2.0

- 两者均为平等开发者，可承担前端、后端、AgentScope、Workflow、Skill、MCP、模型及集成；不固定模块归属。优先 Codex，额度不足或用户需要切换时由 TRAE 继续，反向亦然。执行者直接开发、测试和修复，不因角色要求另一方逐项审查。
- 同一时刻仅一个 AI 负责项目代码和共享状态写入；当前执行者维护 TASKS.md / HANDOFF.md，其他 AI 不同时写入。交班先停止写入并释放，再由接班方接手；只读检查可进行。共享文档是协调记录，不是技术锁。
- 既有 [forecast-engine/share-files/TASKS.md](forecast-engine/share-files/TASKS.md) 和 [HANDOFF.md](forecast-engine/share-files/HANDOFF.md) 是全项目共用的状态入口；沿用原位置避免产生第二套清单。当前执行者更新进度、遗留问题及交班信息，不需重复创建任务目录或多轮分派。
- 已授权的项目任务在执行前，由当前执行者在该任务既有 TASK.md 中拆分具体步骤，标记待做、进行中、完成或阻塞；完成每一步及时记录结果、必要测试和下一步，执行较长步骤前记录当前进展。接班时直接读取该文件、交接摘要和相关 Git 状态，不依赖聊天记录。突发中断时 HANDOFF 可能尚未更新，结合已保存的 TASK.md 与代码状态核实。纯只读咨询不为形式建立任务；若必须新建任务编号或目录，仍先获得用户确认。
- 交接只记录当前任务/进度、已修改文件和 Git 提交或未提交状态、测试结果、未解决问题、下一步。接班以当前代码和交接记录为依据，按需核对 Git，不重做已完成工作或重复讨论既定架构。
- 除用户明确要求，不对每次交付强制跨 AI 审查。当前执行者验证自己的修改；关键里程碑、跨模块集成和正式发布前组织统一验收，业务功能由用户验收。测试未通过或证据不足不能标记相应范围验收通过。
- 新建任务编号/目录先经用户明确确认；同一既有任务可直接接续，不得靠拆号绕过未完成项。用户明确要求先确认的业务或重大决策遵照执行。
- 保持原有市场预测功能；Chronos-2 为新增独立能力。重大架构重构、数据库破坏性变更或删除既有功能前取得用户确认，普通实现由当前执行者判断。先检查 Git 状态，保护已暂存、未暂存及未跟踪成果。
- 保存历史任务、报告与既定验收范围；历史 V1 主从分工、固定文件写入方和强制互审已被 V2.0 取代。非必要不修改旧报告，不做大规模迁移、清理或重复安装。
- 未经授权不提交、推送或部署；不使用 `git add .` 混入其他工作。继续遵守上文凭据、浏览器、业务数据和目录规则。
