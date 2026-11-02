# 竞品对标 Agent 挂载策略

## Agent 定义（2026-11-02 用户确认：新建专用 agent）

- 实现文件：`agents/benchmark_agent.py`（S6 实现）
- 名称：竞品对标智能体
- 技术栈：AgentScope 2.0.3 稳定 API——`Agent` + `ReActConfig` + `Toolkit`；与 `market_strategy_agent` 平级，不经由它转发
- 模型路由（遵循 `utils/model_routing.py`，禁止回退未授权提供方）：
  - L1 / L2 → `deepseek-v4-flash`
  - L3 及复杂多轮取证 → `deepseek-v4-pro`

## 工具挂载

| 工具 | 来源 | 状态 |
|---|---|---|
| `miit_search_models` / `miit_get_model_detail` | 本地只读工具（psycopg2 直连 3.146 `vectordb` / `miit` schema） | S4 已注册 |
| `reputation_*` | 现有 business toolkit | 已有 |
| `web_search_local` / `web_search_exa` / `web_search_tavily` | 现有三级搜索 | 已有 |
| `web_reader_local` / `web_reader_firecrawl` | 现有精读 | 已有 |
| 研究执行引擎接口（任务图/回执/波次） | benchmark_research_dag（机制复制自月报，独立演进） | S3 实现 |

## 调用策略

- 默认任务：接收目标车型 / 发布会事件 / 公告批次 → 按 SKILL.md 四段工作流执行。
- ReAct 迭代上限与引擎波次配合：长循环放引擎侧，单轮 agent 迭代不承担全部取证。
- 界面入口：左侧导航顶级项【竞品对标】（`data-view='benchmark'`，[home.html](../../../home.html) 市场预测组之后），页面与 API 于 S6 交付。
