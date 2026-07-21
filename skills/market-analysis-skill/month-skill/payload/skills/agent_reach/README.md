# Agent Reach 月报证据适配器

本目录将外部的 Agent Reach 能力封装为项目内稳定接口，供市场月报 Skill 和
`tools/custom_tools.py` 共用。

## 运行依赖

- 已安装 `agent-reach`：用于健康检查。
- 已安装 `mcporter`，并已配置 `exa` MCP：用于实际网页搜索与正文抓取。

检查命令：

```powershell
agent-reach doctor --json
mcporter list exa
```

## 调用边界

1. `search()` 只发现公开来源，返回标题、URL、发布日期、摘要与来源等级。
2. `fetch_pages()` 只读取已知 URL 的正文；单页失败不影响月报主流程。
3. A 级为政府、行业协会和中汽体系域名；B 级为行业专业机构；C 级仅作线索。
4. 搜索结果不是结论。月报因果结论必须同时有内部销量事实和带编号的外部证据。

## 不做的事情

- 不读取或写入 `.env`，不处理任何 API Key。
- 不把搜索摘要直接当作中汽数据口径的销量来源。
- 不静默回退到 AnySearch；AnySearch 保持为独立工具，审计日志会明确记录实际提供方。
