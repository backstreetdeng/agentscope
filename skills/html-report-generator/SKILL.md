---
name: html-report-generator
description: "市场分析报告 HTML 演示文稿生成：基于 Markdown 报告生成麦肯锡钴蓝风格的 HTML 演示文稿（全屏幻灯片、键盘翻页、进度条、自定义圆形光标特效），参照 D:\\2024年度工作日志和备忘录\\7.0 吕力\\PPT策划制作与咨询风工作流标准指南.html"
metadata: {"clawdbot":{"emoji":"📊"}, "openclaw": {"tools": ["generate_html_report", "generate_from_markdown"]}}
---

# HTML 报告生成 Skill

> 参照架构：v1.0《汽车市场 AI 智能体架构设计-垂直领域方案》(2026-06-23) - 4.3 Skill 4 配套
> 设计风格参照：D:\2024年度工作日志和备忘录\7.0 吕力\PPT策划制作与咨询风工作流标准指南.html

## 身份与能力边界

- **定位**：把 Markdown 报告一键转换为麦肯锡钴蓝风格的全屏 HTML 演示文稿
- **能做什么**：
  - 把 Markdown 章节（## 章节）拆分为独立 slide
  - 应用麦肯锡咨询风格（钴蓝主色 + Outfit + Noto Sans SC 字体）
  - 实现键盘 / 触摸 / 鼠标滚轮三路翻页
  - 实现进度条 + 页码 `01/07` 格式
  - 集成自定义圆形蓝色光标特效（悬停控件时变大）
  - 输出独立 HTML 文件，支持浏览器 Ctrl+F 搜索
- **不能做什么**：
  - **不修改报告内容**（HTML 输出与 Markdown 一致，不增不删）
  - 不自行生成报告（必须消费 Markdown 输入）
  - 不做战略分析或数据检索
  - 不省略 updateUI() 函数（曾因此缺失导致零跑 HTML 无法翻页）
  - 不省略自定义光标特效（架构要求 + 老大截图要求）

## 触发条件

当编排专家下发的任务包要求 `formats: ["html"]` 或 `formats: ["markdown", "html"]` 时激活，且必须有 Markdown 报告（先调用 `report-generator` 生成，再调用本 skill）。

## 能力上限

- 输出独立 HTML 文件（自包含 CSS + JS，无外部依赖除 Google Fonts）
- 最多支持 100+ slide
- 完整保留 Markdown 报告所有章节
- 7 项校验清单：键盘翻页 / 触摸滑动 / 进度条 / 页码 / 动画 / slides 可访问 / 无 JS 报错
- 自定义圆形光标：32px 圆圈，悬停控件时变大为 52px

## 能力下限（不允许做的事）

- 不允许手动拼接 HTML（必须调用本 skill）
- 不允许省略 updateUI() 函数 + 初始化调用
- 不允许省略自定义光标特效
- 不允许在 HTML 中新增或修改报告内容
- 不允许省略校验清单自检
- 不允许在自检未通过时交付
- 不允许在 HTML 中使用"工具调用成功"等系统术语

## 执行流程

1. **接收 Markdown 报告** → 校验文件存在且非空
2. **解析章节** → 按 `## ` 切分为 slides 列表，封面（`#`）作为第一个 slide
3. **生成 HTML** → 注入麦肯锡钴蓝 CSS + 全屏 deck 布局 + JS 翻页逻辑
4. **强制包含三项关键代码**：
   - `updateUI()` 函数 + `DOMContentLoaded` 初始化调用
   - 自定义光标 `<div class="cursor" id="cursor"></div>` + CSS + JS 跟踪
   - 页码 `01/07` 零填充 + 进度条 width 同步
5. **写入文件** → UTF-8 编码，无 BOM
6. **7 项校验清单自检**（详见下方"质量门"）
7. **确认无误后交付** → 失败则修复后重生成

## 决策规则

| 情况 | 动作 |
|---|---|
| Markdown 文件不存在或为空 | 抛出 ValueError，记录 errors |
| Markdown 解析不出任何 ## 章节 | 抛出 ValueError，记录 errors |
| 7 项校验任一失败 | 修复后重新生成，不得绕过校验直接交付 |
| 编排要求只交付 HTML | 必须先有 Markdown（内部消费 `report-generator` 输出） |

## 输出格式

```json
{
  "success": true,
  "html_path": "E:\\xxx\\报告名.html",
  "file_size": 30285,
  "slides_count": 8,
  "validation": {
    "keyboard_navigation": true,
    "touch_swipe": true,
    "progress_bar": true,
    "page_indicator": true,
    "animations": true,
    "all_slides_accessible": true,
    "no_js_errors": true,
    "update_ui_function_defined": true,
    "update_ui_initialized": true
  },
  "features": {
    "custom_cursor": true,
    "google_fonts": true,
    "mckinsey_blue_theme": true,
    "responsive": true
  }
}
```

## 质量门（7 项校验清单）

生成后必须自检通过才能交付：

| 检查项 | 验证方法 | 失败影响 |
|---|---|---|
| 键盘翻页 ←→ | 按方向键，进度条和页码同步更新 | 无法翻页 |
| 触摸滑动 | 移动端左右滑动 | 移动端失效 |
| 进度条更新 | 翻页后 width 变化 | 失去位置感 |
| 页码显示 | 格式 `01/07` 零填充 | 显示混乱 |
| 动画效果 | slide 切换 fade + translateY | 体验生硬 |
| 所有 slides 可访问 | 逐页翻阅 | 部分内容丢失 |
| 无 JS 报错 | Console 无红色错误 | 功能异常 |
| 自定义圆形光标 | 鼠标显示蓝色圆圈，悬停控件时变大 | 失去品牌特色 |

**updateUI() 函数是核心**：所有 `goTo` / `next` / `prev` 内部必须调用 `updateUI()`，且 `DOMContentLoaded` 时必须初始化调用一次（已写入 html_report_generator.py）。

## 与其他 Skill 的交接协议

| 上游 | 接收 | 协议 |
|---|---|---|
| report-generator | markdown 字符串 + report_title | 必须先有 Markdown，HTML 不修改内容 |
| strategy-orchestrator | 任务包 | `formats: ["html"]` 或 `["markdown", "html"]` 时调用 |

| 下游 | 返回 | 协议 |
|---|---|---|
| strategy-orchestrator | html_path + file_size + slides_count + validation | 双版本交付时同时返回 markdown 和 html 路径 |
| 用户 | 独立 HTML 文件 | 可在浏览器中直接打开使用 |