# TRAE 使用 146 堡垒机 SSH 操作指南

整理日期：2026-10-30。用途：让 TRAE 在用户授权的具体任务中，复用已有的 `server146-bastion-ssh` 连接脚本。本指南是操作交接，不是独立的 SSH 程序，也不是执行服务器操作的授权。

## 1. 先读取完整技能包

在本机，完整技能位于：

```text
C:\Users\legio\.codex\skills\server146-bastion-ssh\
├── SKILL.md
├── scripts\run.ps1
├── scripts\server146.py
├── assets\bastion_known_hosts
└── references\runbook.md
```

TRAE 应先实际读取 `SKILL.md`，需要排障或部署时再读取 `references\runbook.md`。不要只把本 Markdown 当作完整技能；脚本、固定的堡垒机公钥和运行手册是功能的一部分。若 TRAE 可以访问同一 Windows 用户目录，直接复用上述包；若处于另一用户、容器或其他电脑，需要让运行环境能访问完整技能包及受控凭据，并重新检查依赖和连通性。不要复制或提交凭据。

原技能包中提到的 `C:\Users\11489\...` 是历史机器示例，不是本机路径。目录和可访问性以实际运行账户核实结果为准。

## 2. 连接路径和核验

```text
本机 Python + Paramiko
  → 堡垒机 192.168.3.243:60022
  → GateShell 授权资产 root@192.168.3.146:12816
  → 核验用户 root、主机名 ubuntu-virtual-machine、IP 192.168.3.146
  → 执行本次任务授权的操作 → 退出目标及堡垒机
```

原技能记录的是 2026-10-09 的历史验证，不能据此断言当前网络、凭据及服务器状态仍有效。不要默认直连目标 22 端口，也不要假设堡垒机支持 ProxyJump 或 SFTP。连接时固定校验 `assets\bastion_known_hosts`；公钥未知或变化时停止，核实可信指纹，不自动接受或关闭校验。

## 3. 本机前提及当前检查结果

2026-10-30 本次仅检查文件是否存在，没有读取或展示凭据，也没有连接服务器：

| 项目 | 本次结果 |
| --- | --- |
| 技能说明、`run.ps1`、公钥文件 | 存在 |
| Codex 默认 Python 路径 | 存在；版本和运行效果尚未在本次验证 |
| `%LOCALAPPDATA%\Codex\ssh-146\python-packages\paramiko\__init__.py` | 不存在，默认依赖目录尚未就绪 |
| 默认凭据文件 `C:\deng\.env` | 不存在；不能据此推断其他位置是否有可用凭据 |

默认 Python 路径是 `%USERPROFILE%\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe`。所需 Paramiko 安装方法及版本见原技能的 `references\runbook.md`；先确认本机环境，按实际任务授权处理依赖，不在每次连接时自动升级。不要为排障关闭 TLS 或 SSH 主机校验。

默认从 `C:\deng\.env` 读取 `BASTION_USER` 和 `BASTION_PASSWORD`；兼容密码字段 `KEY`。`KEY` 是字段名，不是登录用户名；目标 root 也不是堡垒机用户名。用户明确指定另一凭据文件时，可用 `-Credentials` 指定该文件路径。缺少用户名或密码时只说明缺什么，让用户通过受控方式配置；不要要求在聊天中发送密码，不输出凭据文件内容、密码或验证码，也不将其写入命令文件、日志、文档或 Git。

## 4. 用户只授权连接检查：probe

前提准备齐备后，在 PowerShell 执行：

```powershell
& "$env:USERPROFILE\.codex\skills\server146-bastion-ssh\scripts\run.ps1" -Mode probe
```

使用用户明确提供的其他凭据文件时：

```powershell
& "$env:USERPROFILE\.codex\skills\server146-bastion-ssh\scripts\run.ps1" -Mode probe -Credentials '替换为用户提供的凭据文件路径'
```

脚本只运行 `id -un`、`hostname`、`hostname -I` 等身份核验。必须观察到 `target_verified` **和** `probe_succeeded` 才能报告目标连接核验成功；只有 `bastion_authenticated` 说明堡垒机认证成功，不能代表已连上目标。记录脱敏结果与退出状态，不记录敏感值。

## 5. 已授权的检查或运维：exec

只有用户已明确授权相应目标和操作范围时，才执行命令。先将准确命令写入当前项目内的 UTF-8 文件（运维命令放 `ops/`；一次性命令放项目规定的 `temp/` 任务目录并附用途说明），再调用：

```powershell
& "$env:USERPROFILE\.codex\skills\server146-bastion-ssh\scripts\run.ps1" -Mode exec -CommandFile '替换为本项目命令文件的实际绝对路径' -TimeoutSeconds 120
$exitCode = $LASTEXITCODE
```

也可加 `-Credentials '用户明确提供的凭据文件路径'` 或 `-Python '已核实的 Python 3.12 路径'`。命令文件不超过 16 KiB，所有内容在一次独立 `bash -c` 会话内执行；跨次调用不保留 `cd` 和环境变量。需要遇错停止时在命令文件中使用 `set -e` 或 `set -euo pipefail`，并单独处理预期允许失败的检查。实际远端退出码以 `command_result.exit_code` 为准；外层 PowerShell 包装可能将非零进程退出码统一显示为 1。

部署或升级前应核实服务、当前及目标版本、路径、数据影响和回退方法，执行后核查实际服务状态及健康结果。已有明确授权覆盖的常规步骤可继续；目标或版本等必要信息缺失时先做独立的只读检查，再询问缺项。不能因为能以 root 登录而扩大任务范围。

## 6. 故障及数据边界

- GateShell 的资产命令需要逐字发送并以 CR 结束；现有脚本已处理，不用临时交互脚本猜测替代。
- 认证失败立即停止，不循环尝试账号密码；资产菜单、目标身份或主机公钥不符时停止并核实。
- 执行超时或断连时，远端操作结果可能未知：先只读核查实际状态，再决定恢复；不要自动重跑部署、重启或迁移。
- 输出最多 2 MiB，超长日志需由已授权命令限制范围；正常退出信息和远端退出码应分别记录。
- 146 的业务数据库、政策库及已注册共享文件仍通过 `foundation-sandbox` 等对应技能及权限访问，不借 SSH 绕过业务数据限制。
- 不关闭月报浏览器、不重启既有服务、不执行未授权的数据库或业务数据修改；遵守项目 `AGENTS.md` 及当前任务交接状态。

## 7. 发给 TRAE 的任务示例

```text
请先读取 myproject/docs/server146-trae-ssh-guide.md 及其中指向的完整
server146-bastion-ssh/SKILL.md。检查本机运行前提；按我本次明确授权的范围操作。
如果我只要求测试连接，就只运行 probe 并核实目标身份；缺少凭据或依赖时报告缺项，
不要输出凭据。不要将仅堡垒机认证成功报告为已连接 146。
```

本指南由 Codex 根据本机技能包整理；本次没有安装依赖、登录堡垒机、验证 146 或修改服务器。
