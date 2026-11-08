# 竞品洞察任务总表 · tasks

- 更新：2026-11-07（Asia/Shanghai）
- 本表统一维护所有任务的编号、标题、当前阶段、负责人、最后更新时间与下一步。
- 与各 `BCI-NNN/TASK.md`、[BOARD.md](../BOARD.md) 必须逐项一致；冲突时以 `TASK.md` 为准并回改本表。`check_board.py` 会校验三方一致。
- 阶段含义与准入条件见 [RULES.md](../RULES.md) 第 6 节。

| 编号 | 标题 | 阶段 | 负责人 | 更新时间 | 下一步 |
|---|---|---|---|---|---|
| [BCI-001](BCI-001/TASK.md) | 竞品洞察 · 数据源筛选 tab | TESTED | TRAE | 2026-11-06 | 用户验收 7860 页面后确认上线 |
| [BCI-002](BCI-002/TASK.md) | 深访用户洞察档案模板（两份：新能源 / 用户洞察档案） | TESTED | TRAE | 2026-11-06 | 用户验收 7860 页面下拉两条模板均可选后确认上线 |
| [BCI-003](BCI-003/TASK.md) | 学习 DeepSeek Harness 工程方法并评估对竞品洞察的适用性 | DEV_DONE | TRAE | 2026-11-06 | 用户阅读 docs/harness-study.md 的 Q3/Q5 与 §5 全 workspace 复核（含 5 条建议修正 + 新增 #6/#7），确认是否立项落地 |
| [BCI-004](BCI-004/TASK.md) | 竞品洞察 · 用户洞察档案 tab | TESTED | TRAE | 2026-11-07 | 用户验收 7860 页面与 10 人试点数据后确认上线 |
| [BCI-005](BCI-005/TASK.md) | 竞品洞察 · 任务机制 Harness 化（契约 reader/verify、三态计数、冻结路径） | DEV_DONE | TRAE | 2026-11-06 | 用户复核 TASK-COMMITTED 与反向验证记录；存量任务须先统一入库，本任务才能转 TESTED |
| [BCI-006](BCI-006/TASK.md) | 竞品洞察 · 即时分析 tab | TESTED | TRAE | 2026-11-08 | 用户明早验收 7860「即时分析」tab；业务确认 §8 数据缺失清单的后续补数范围 |

## 维护约定

1. 新建任务：先写 `tasks/BCI-NNN/TASK.md`，再在本表加一行，最后在 `BOARD.md` 对应阶段栏加一行。
2. 阶段变化：改 TASK.md 状态块 → 改本表阶段/更新时间/下一步 → 移动 BOARD 分栏，三处同一批完成。
3. 本表只放一行摘要，不写步骤、证据、遗留细节；那些在 TASK.md 与证据目录。
4. 不新增第二个任务总表；`forecast-engine/share-files/TASKS.md` 只保留指向本目录的一行指针。
