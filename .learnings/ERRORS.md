# 错误与修复记录

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
