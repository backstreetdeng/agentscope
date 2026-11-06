# 竞品洞察 · 任务制工作区（BCI）

本目录是「竞品洞察」这条业务线的唯一入口：代码、任务、看板、规范、证据索引都在这里。竞品洞察的开发、修复、验证、上线都以任务推进，不再用临时对话承载状态。

- [RULES.md](RULES.md)：规范——代码落点、什么必须落任务、状态谁能改、阶段准入、交接、遗留挂账。
- [tasks/tasks.md](tasks/tasks.md)：**任务总表**（编号 / 标题 / 阶段 / 负责人 / 更新时间 / 下一步）。
- [BOARD.md](BOARD.md)：全局看板，按阶段分栏，并聚合未关闭的遗留项与阻塞。
- [HANDOFF.md](HANDOFF.md)：最近一次交接摘要。
- `tasks/<任务编号>/TASK.md`：**单个任务的唯一状态文件**；`tasks/tasks.md`、看板、交接都不是状态源。
- `tasks/_TEMPLATE/TASK.md`：新任务模板。
- [web/](web/)：竞品洞察专属前端资源（`bci.js`、`bci.css`），经 `/competitor-insight/` 路由提供。
- `server/`：竞品洞察专属后端实现（有代码时才建，路由注册仍留在 `app.py`）。
- [check_board.py](check_board.py)：只读一致性检查（`tasks.md` ↔ `BOARD.md` ↔ 各 `TASK.md` ↔ 证据路径）。

## 30 秒上手

1. 先看 [tasks/tasks.md](tasks/tasks.md) 与 [BOARD.md](BOARD.md)，知道每个任务在哪个阶段、谁在做、卡在哪。
2. 再读该任务的 `TASK.md`：顶部状态块是唯一事实，步骤与结果、证据索引、遗留挂账都在里面。
3. 动手前按 [RULES.md](RULES.md) 第 3 节判断是否必须先建任务；新编号需用户确认。
4. 每完成一个阶段：改 `TASK.md` → 同步 `tasks.md` → 改 `BOARD.md` → 回声一次；交付前跑 `../Scripts/python.exe -B competitor_insight/check_board.py`。

## 边界

- 项目级规则与轮班接力以根 [AGENTS.md](../AGENTS.md) 为准；本目录只补充竞品洞察这条线。
- 智能问答共用底座（`quant_service`、`retrieval_service`、`insight_service`、`segment_aliases`）留在 `customer_insight/`，竞品洞察通过 import 引用，不搬迁。
- 市场预测/Chronos 任务在 `forecast-engine/share-files/tasks/`（CHRONOS-xxx），【竞品对标】在 `MKT-001`，本目录不接管。
- 大体积证据放 `outputs/competitor-insights/<任务编号>/<run-id>/`，`TASK.md` 只存链接与结论。
