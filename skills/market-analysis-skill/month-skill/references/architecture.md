# 安装包架构

## 运行链路

```text
用户问题/分析类型
  -> MarketAnalysisSkill.should_activate
  -> 数据源和月份选择
  -> Excel解析与输入门禁
  -> TOP15代表车型筛选
  -> 内部研究证据加载
  -> 必要时Agent Reach外部检索
  -> 业务Profile + 数据事实 + 证据边界注入MiniMax-M3
  -> Markdown月报正文
  -> 输出门禁与展示清理
  -> 业务母版PPTX渲染
  -> 可编辑PPTX与审计结果
```

## 六个责任边界

| 模块 | 负责 | 不负责 |
| --- | --- | --- |
| `SKILL.md` | 触发、流程、行为约束 | 具体数据解析 |
| `runtime.py` | 数据、门禁、证据上下文 | Web UI 与模型密钥 |
| `page_specs.yaml` | 页面业务定义 | PowerPoint XML 操作 |
| `monthly_report_pptx.py` | PPTX 原生对象更新 | 生成市场原因 |
| 宿主 Agent | 调用模型、返回正文 | 偷改数据和模板 |
| 宿主 Web | 交互、日志、文件下载 | 业务规则真值 |

## 安装边界

安装器只合并 `payload/` 和业务 Profile，不自动修改：

- `.env`；
- MiniMax API Key；
- 宿主 `app.py` 或前端；
- 数据库、文件库和向量库连接；
- 现有 `model_config/config.json`。

这样可以把代码安装与宿主系统接线分开审查。

## 当前技术债

当前五页渲染器仍以显式函数映射页面；`page_specs.yaml` 是扩展契约和单一业务说明源，但尚未完全驱动所有 Python 逻辑。下一版本应把页面解析、章节提取和渲染 handler 注册化，减少新增页面时对主渲染器的修改。
