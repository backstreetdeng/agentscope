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
