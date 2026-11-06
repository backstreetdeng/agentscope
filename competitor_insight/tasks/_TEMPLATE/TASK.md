# BCI-XXX：一句话任务名

```
task_id: BCI-XXX
title: 一句话任务名
stage: CREATED
owner: TRAE
port: none
frozen_paths: none
commit_paths: none
updated: YYYY-MM-DD
blocked: no
next: 第一家可执行动作
evidence: none
```

> 模板用法：复制本目录为 `tasks/BCI-NNN/`，替换编号与标题；再在 `tasks/tasks.md` 与 `BOARD.md` 对应阶段栏各加一行并保持字段逐字一致。顶部状态块是唯一状态源，字段含义见 [RULES.md](../../RULES.md) 第 5 节。
>
> `port`：本任务运行/验证占用的端口，不占用写 `none`；两个非终态任务不得声明同一端口。
> `frozen_paths`：本任务**不得改动**的文件，逗号分隔，不限制写 `none`。声明后先运行 `python -B competitor_insight/check_board.py --freeze BCI-NNN` 建立 sha256 基线，之后任何改动都会被检查器判 FAIL。存量任务未写这两项时按「未声明 = 不限制」处理。
>
> `commit_paths`：本任务的文件集，用于入库判定。`TESTED` 前必须本地提交、`LIVE` 前必须推送远程；处于这两个阶段时若未声明或仍有未提交/未跟踪文件，`TASK-COMMITTED` 约束会 FAIL。

## 1. 目标与边界

- 目标：要交付的可观测结果（用户能看到/能调用到什么）。
- 边界：明确不做什么；涉及共享文件时写影响面。
- 禁止项：不得改动的文件、数据、开关、服务。

## 2. 验收标准（必须可判定）

| # | 验收项 | 判定方式 | 证据要求 |
|---|---|---|---|
| A1 |  |  |  |

## 3. 步骤与结果

| # | 步骤 | 状态 | 实际结果 | 证据 |
|---|---|---|---|---|
| S1 |  | 待做 |  |  |

## 4. 证据索引

- 证据目录：`outputs/competitor-insights/BCI-XXX/<run-id>/`
- manifest：`manifest.json`
- 只读探查脚本：`temp/<YYYYMMDD>-<slug>/`（说明用途与可否清理）

## 5. 已知边界（不是缺陷，但下游必须知道）

- 数据覆盖、样本量、口径限制等。

## 6. 遗留问题

| 编号 | 问题 | 影响 | 现状 | 解除条件 | 负责人 | 证据/关联 |
|---|---|---|---|---|---|---|
| BCI-XXX-L01 |  |  |  |  |  |  |

## 7. 阶段流转记录

| 日期 | 阶段 | 依据 | 证据 | 变更人 |
|---|---|---|---|---|
|  | CREATED |  |  |  |
