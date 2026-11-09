# HelloAgent 研发任务索引 · V2.0

全项目复用此清单，当前值班 AI 负责维护；共同规则见 [AGENTS.md](../../AGENTS.md)，最近交接见 [HANDOFF.md](HANDOFF.md)。此处只列已纳入该研发清单的事项，不代表穷尽项目全部业务需求。

## 当前值班与交接

- 当前写入方：Codex（当前聊天直接执行，非后台委派）；按CHRONOS-003/TASK.md顶部“记分卡与交付收口”步骤推进。已有回执复用，内置浏览器故障不阻塞记分卡和接口验证。
- 交接状态：Chronos-2 可在主服务、独立预览及 CLI 内运行；按用户要求已启动仅本机监听的 7860 主服务并实测。业务精度和用户验收仍待完成。V2.0 规则终版已提交推送（`d078967`），本任务未提交。2026-11-02 用户确认市场板块新增竞品对标能力并立项 MKT-001（不沿用预测引擎前缀，MKT 系列自 001 起），需求文档 v0.1 待评审。
- 工作原则：同一时刻一个 AI 写代码及共享状态，文件不同也不自动构成并行许可；本记录不是操作系统锁。额度不足或用户需要切换时，接班方读取 TASK/HANDOFF 和 Git 后继续。

## 任务索引

| 任务 | 状态和验收范围 | 当前执行 / 下一步 | 任务文件 |
| --- | --- | --- | --- |
| CHRONOS-001 | 模型边界及本地 CPU 离线回归已验收；业务精度、网页/API/Agent 集成未验收 | 已完成本范围；后续实际需求由当前值班 AI 接续 | [TASK.md](tasks/CHRONOS-001/TASK.md) |
| CHRONOS-002 | 第一阶段功能开发及技术验证已归档；真实数据回测参考门槛未达，业务精度和用户验收未完成 | 保留历史记录和遗留问题，业务验收按后续安排继续 | [TASK.md](tasks/CHRONOS-002/TASK.md) |
| CHRONOS-003 | 进行中；本月目标调整为可用市场预测闭环，已有预测/回测/助手成果复用，业务精度仍待验收 | 11/10主流程演示 → 11/17解读闭环 → 11/24候选版 → 11/30交付验收；政策/价格批量补核不阻塞，油价保留试验不正式启用 | [TASK.md](tasks/CHRONOS-003/TASK.md) |
| MKT-001 | 竞品对标能力（市场板块新增）；**已接入**（skill-integration-standard 12 项全部满足：S0–S8 完成，引擎/数据工具/规则库/agent+API+页面/skill runtime 隔离运行+run_id 恢复+回放/独立验收全部落地；双引擎共存冒烟 + 真实模型执行验收 PASS；月报 git 零改动已核查） | 已完成 | [TASK.md](tasks/MKT-001/TASK.md) |
| MKT-002 | 深度调研能力（deep-research Skill，2026-11-06 用户确认立项）：确定性编排（模型仅 2 次受限调用，代码取证+引用清理+独立验收），双源搜索 any_search→tavily，端到端 78s/103s 验收 passed，单测 12/12，技能页+工作区入口已接 | 已交付（遗留 L01–L04 见 TASK.md） | [TASK.md](tasks/MKT-002/TASK.md) |
| BCI-001 | 竞品洞察线首个任务（数据源筛选 tab）；四类数据源与模板选择器，浏览器验收 39/39 通过，2026-11-06 首批入库 | 测试通过（待上线）；后续阶段与遗留以 [competitor_insight/BOARD.md](../../competitor_insight/BOARD.md) 为准 | [TASK.md](../../competitor_insight/tasks/BCI-001/TASK.md) |
| BCI-002 | 深访用户洞察档案模板两份（新能源 v1：8 组 43 维；用户洞察档案），浏览器验收 39/39 通过，2026-11-06 首批入库 | 测试通过（待上线）；后续以 [competitor_insight/BOARD.md](../../competitor_insight/BOARD.md) 为准 | [TASK.md](../../competitor_insight/tasks/BCI-002/TASK.md) |

**竞品洞察线（BCI 系列）自 2026-11-06 起采用独立任务制**：任务、看板、规范、交接统一在 [competitor_insight/](../../competitor_insight/README.md)，任务总表为 [tasks/tasks.md](../../competitor_insight/tasks/tasks.md)；本清单只保留指针，具体阶段与遗留不在两处重复维护。

CHRONOS-001 的 T001、C001 已关闭；C002 的 GPU、并发、资源及精确 revision 未验证。历史结果见原 [TRAE_REPORT.md](tasks/CHRONOS-001/TRAE_REPORT.md) 和 [CODEX_REPLY.md](tasks/CHRONOS-001/CODEX_REPLY.md)，这些文件不再是强制交接材料。

## 本次规则调整（无新任务编号）

- [x] 核对现有规则、Git 状态及既有任务。
- [x] 统一 AGENTS.md 与 V2.0 单执行者、平等接力规则。
- [x] 更新兼容入口、共享索引及交接摘要，保留历史任务和报告。
- [x] 检查文档链接、现行规则冲突、暂存区及受保护文件，记录交接并释放写入。

开发任务开始前在对应 TASK.md 记录步骤，执行中逐步更新；未完成任务不得通过另起编号绕过。用户此前要求新建任务编号/目录先获明确确认，此规则继续有效。用户授权的当前任务可直接接续，不需另一 AI 重新分派。

原有市场预测功能保留，Chronos-2 是独立能力。用户确认省份销量为零售、单位辆、插混含增程，并同意已出现月份的缺失省份/类别按零处理；四类小计不含燃料电池。数据及精度边界见 CHRONOS-002。未经授权不提交、推送或部署。
