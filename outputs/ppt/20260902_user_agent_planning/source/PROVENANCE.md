# 来源与生成方式

本目录用于维护两份独立汇报HTML，不属于智能体运行时代码。

- 内容来源：`myproject/doc/plans/20260902_用户洞察与需求配置匹配智能体_项目规划_v1.md`、`20260902_用户智能体规划初版_逐页改进清单.md`。
- Skill：`html-ppt`，安装路径 `C:/Users/11489/.codex/skills/html-ppt-skill`。
- 完整模板：`presenter-mode-reveal`；主题：`corporate-clean`。
- 组合版式：`flow-diagram`、`comparison`、`roadmap`、`arch-diagram`。原始模板副本保存在 `vendor/`。
- `vendor/base.css`、`vendor/runtime.js` 与模板为只读来源副本。生成器仅在内存中调整缩略图布局类、内边距和演讲者字距，不修改Skill安装目录。
- 演示使用固定企业主题，因此未启用依赖外部CSS文件的主题轮换；运行时、主题、样式和图标全部内联。
- 图标来自Lucide，`icons.json`是本次用到的图标节点数据，不依赖CDN或浏览器运行时安装。
- 授权说明：见 `vendor/LICENSE-html-ppt.txt` 与 `vendor/LICENSE-lucide.txt`。

## 可维护文件

- `planning.cjs`：22页规划汇报内容、讲稿和来源章节。
- `review.cjs`：14页评审稿内容、讲稿和原11页对应关系。
- `deck.css`：本地主题与布局调整，固定1920×1080画布整体缩放。
- `client.js`：缩放、图标控件和移动端滑动；核心翻页/讲稿/演讲者逻辑沿用Skill。
- `build.cjs`：基于模板编译两份单文件HTML及 `source-map.json`。
- `verify.cjs`：使用Playwright、Chrome与Sharp检查离线资源、逐页布局和控件，生成检查记录与缩略图。

构建仅需Node.js：在此目录执行 `node build.cjs`。验证另需能解析 `playwright` 和 `sharp` 包，并已安装Google Chrome；必要时通过 `NODE_PATH` 指向本机已有依赖目录。无需修改项目Python环境。

本次检测到默认Playwright自带Chromium未安装，因此验证显式使用已有Google Chrome（`channel: 'chrome'`），没有下载浏览器或改动任何Python环境。
