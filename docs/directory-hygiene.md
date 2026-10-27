# 目录与文件管理规则

更新日期：2026-10-27。本规则适用于 `myproject`；父目录是 Python 环境，不作为本项目临时区。机器可读根目录白名单以 [root-files.json](root-files.json) 为准。

## 当前生效规则

| 内容 | 放置位置 | 生命周期与清理条件 |
| --- | --- | --- |
| 项目说明、开发规则、启动入口、依赖与根配置 | 根目录白名单 | 长期保留；迁移前修改全部调用方 |
| 正式业务 Python | 现有 agents/tools/utils/integrations 等模块 | 源码，使用 Git 管理，不能当作临时脚本删 |
| 开发、生成、检查和启动辅助脚本 | scripts/ | 文件开头说明用途、输入、输出、副作用；不硬编码旧电脑路径 |
| 部署、导入、服务器维护 | ops/ | 默认不直接发布或写业务库，按任务授权执行 |
| 自动化测试 | tests/ | 依改动运行有意义的验证 |
| 新增正式 HTML 页面 | pages/ | 同步注册路由、资源路径和页面测试；保持用户访问 URL 明确 |
| 现有根目录七个 HTML | 白名单 legacy_pages | 当前服务直接读取，作为独立迁移批次处理，整理时不挪动 |
| 正式 CSS/JS/图片 | assets/ | 仅存网页运行资源；截图不混入 |
| 当前维护说明 | docs/，入口见 docs/README.md | 长期文档更新同一真源；历史材料进入 docs/history/ |
| 原始技能包和参考材料 | skills/、reference_project/、既有 doc/ | 保留包内结构与只读边界，不按扩展名拆散包 |
| 日志 | logs/<服务名>/ 或 logs/archive/<日期-任务>/ | 先确认写入方停止、无占用；无继续诊断/审计需要后再列清理清单 |
| 报告、检查结果、交付物 | outputs/<任务>/<批次>/ | 写 README/manifest；已交付不等于不需要保留，按验收和追溯要求处理 |
| 截图、渲染页、临时 HTML 成品 | 对应 outputs 任务下 screenshots/、rendered/ 等 | 随所属任务一起说明来源和保留条件；旧 screenshots/ 作历史归档 |
| 一次性脚本、试稿、中间文件 | temp/<YYYYMMDD-task>/ | 记录复现命令；任务完成、无引用、可重建后才列入可清理项 |
| 必要备份 | backup/<YYYYMMDD-task>/ | 记录原路径、SHA256 和恢复方法；禁止覆盖新文件恢复 |
| 任务状态、检查点、浏览器会话 | runtime/ | 恢复依据，禁止按年龄或大小清理 |
| 稳定数据与业务台账 | data/ | 不作为缓存清理；变更须有业务授权 |

不创建把所有 Python 混装的 `py/` 目录；代码按职责分模块，辅助脚本统一放 `scripts/`。使用已有的 `logs/`，不再建立第二个 `log/`。

## 每次任务的执行要求

1. 先查看 Git 状态，确定 `task_id` 和落点，再创建文件。任何新根目录文件必须有明确入口必要性，不得用放宽白名单掩盖杂项。
2. 任务输出目录至少有 `README.md` 或 `manifest.json`，说明目的、来源、生成命令、当前状态、是否可重建、保留/清理条件。可使用 [清单模板](artifact-manifest-template.json)。不在说明中写 Token、Cookie、口令和业务原文。
3. 长期规则或架构说明更新 `docs/` 中同一文件；单次执行记录放任务 outputs。临时脚本升级为可复用工具后迁入 scripts 并补用法，避免 `test2.py`、`final_new_v3.html` 之类无用途名称。
4. 移动前检查入口、源码、配置、文档和活动进程引用；验证路径均在本项目内。不要仅按 `.py/.html/.md` 后缀移动文件。
5. 文件移动保存 source、destination、字节数、SHA256；内容修改分别记录原始与最终哈希。移动不覆盖目标；恢复先核对哈希并确认原路径没有后来生成的新文件。
6. 交付前执行根目录检查和对应行为检查。根目录检查只盘点，不读取凭据，也不删除、移动或重启服务：

```powershell
../Scripts/python.exe -B scripts/workspace_hygiene.py
# 查看每项用途的完整清单；只打印文件名及分类
../Scripts/python.exe -B scripts/workspace_hygiene.py --json
```

检查退出码 1 表示出现未登记根目录项目，需要归位或说明真正的入口用途。检查通过只代表落点已登记，不代表业务功能通过验收。

## 保留状态

- **保留**：正式源码、配置、业务数据、已交付报告、会话和恢复记录。
- **完成后可清理**：已说明复现方法的临时文件；仍需确认无引用、无占用、无需追溯。
- **待核实**：用途或调用关系不清的旧文件；先标记并查证，不擅自删除。
- 任何永久删除均以显式清单为范围，不使用 `git clean -fdx`、按年龄整目录删除或整体忽略输出目录。

## 2026-10-27 已整理批次

迁移清单与验证记录位于 `outputs/directory-hygiene/20261027/`：历史根目录日志进入 `logs/archive/20261027-root-organize/`，三张历史截图进入 `screenshots/archive/20261027-root-organize/`，旧 HTML 备份进入 `backup/20261027-root-organize/`，历史待办进入 `docs/history/`，辅助 Python/BAT 进入 `scripts/`。

根目录正式页面、app/main、启动入口、MCP 配置入口及根配置保留。`_build3/`、`.work/`、`runtime/`、技能历史副本等未做整目录清理；它们在白名单说明中标为历史/恢复资料，后续按具体任务核实。整理不重启网页、不关闭月报 Chrome、不改业务数据。

## 2026-10-20 历史盘点（仅保留记录）

下文是上一轮的历史决策与统计，当前文件落点以本文上半部分和机器白名单为准。

盘点日期：2026-10-20。此文约束 myproject，不修改父目录 Python 环境。

## 当前判断

根目录同时存在正式页面、启动入口、历史源码备份、端口调试日志和临时截图。Git 已存在大量未提交改动，因此不能用“未跟踪”判断文件是否可删除。

按实际文件长度汇总（不等于磁盘占用）：runtime 约 2803.7 MiB / 59128 文件，outputs 约 1583.3 MiB / 10695 文件，.work 约 473.9 MiB / 7518 文件，skills 约 246.2 MiB。空间治理应优先审查运行副本和历史产物；移动几个根目录备份只改善整洁度，不释放空间。

## 文件落点

| 位置 | 用途 |
| --- | --- |
| 根目录 | app.py、main.py、现有 HTML 页面、启动入口、依赖清单及根配置 |
| agents / integrations / tools / utils / model_adapters / skill_runtime | 按现有职责维护业务代码 |
| assets | 页面正式静态资源 |
| scripts | 开发、构建、验证及本机启动脚本 |
| ops | 发布、导入、服务器运维脚本 |
| tests | 自动化测试 |
| skills | 可执行技能包、资源和契约；不要直接合并近似名称目录 |
| docs | 新的维护说明；既有 doc 暂保留，迁移前核查引用 |
| maintenance | 现有专项维护资料；新通用说明放 docs |
| data | 业务状态、稳定数据，禁止作为缓存清理 |
| runtime | 运行工作区、浏览器会话、任务恢复资料 |
| logs | 运行日志 |
| outputs/<task>/<run-id> | 报告、截图、导出文件、验证证据 |
| temp/<YYYYMMDD>-<task> | 可再生成的一次性中间文件 |
| backup/<YYYYMMDD>-<task> | 带来源和恢复清单的必要备份 |

## 分阶段整理

1. 本轮仅归档根目录未跟踪的显式 `.bak` 备份，清单写入 `backup/root-cleanup-20261020/manifest.json`。原文件内容不变；恢复前比较目标状态，目标存在时不可直接覆盖。
2. 根目录日志保留：历史日志名可能仍被启动或诊断脚本使用，也可能正被进程持有。后续逐个确认写入方停止后，再迁往 logs 并修改写入配置。
3. `_shot.py`、`new-car-detail.ui-v1.bak.html` 属于已跟踪文件，临时截图和 `_build3` 的用途尚未完整核实，本轮保留。迁移需检查代码、HTML、配置、启动器及外部调用。
4. `.work`、runtime 内任务副本、outputs 多版报告逐任务核实：确认任务完成、交付物验收、恢复证据不再需要，再列清单归档或删除。浏览器 profile、认证状态、业务数据不进入通用清理名单。
5. skills 下名称相近的包可能有打包/发布关系，须先验证契约和引用。doc/docs、maintenance/ops 的现有内容也不批量合并。

## 执行与恢复

从项目目录运行父环境 `../Scripts/python.exe`。启动采用现有 start_agent.cmd；整理过程中不重启服务。

本轮归档清单记录 source、destination、SHA256 和字节数。恢复时逐条检查归档文件哈希、确认源路径不存在，再用 PowerShell `Move-Item -LiteralPath <destination> -Destination <source>`。所有路径必须解析到本项目内部，禁止覆盖后来生成的新版本。

清理不等于屏蔽 Git 状态：不整体忽略 outputs、data、skills 或 runtime，以免掩盖应审查的业务文件。新增忽略项仅覆盖本地 .work、此次归档及明确的备份后缀。
