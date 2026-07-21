# AgentScope 2.0.3 接入说明

## 版本约束

- 固定 `agentscope==2.0.3`。
- 模型使用 OpenAI 兼容接口，由宿主工程创建和配置。
- 不使用 2.0.4 dev 的临时构造参数、实验工具协议或未稳定底层对象。

## Agent 调用前

```python
from skills.market_analysis_skill import MarketAnalysisSkill

skill = MarketAnalysisSkill(config)
context = skill.prepare(
    question=user_question,
    analysis_type="market_monthly_report",
    sheet_name="6月",
    include_external_evidence=True,
)

if context.input_gate() == "阻断":
    raise RuntimeError("月报输入门禁未通过")

agent_task = user_question + "\n\n" + context.prompt_context
```

将 `agent_task` 交给当前项目已经验证的 AgentScope 2.0.3 Agent。模型与 Agent 构建方式继续由宿主工程负责，安装包不覆盖。

## Agent 返回后

```python
checks = skill.validate_report(report_text, context)
if context.output_gate() in {"阻断", "风险"}:
    # 返回业务修订或人工复核，不直接发布PPTX
    pass
```

## 生成可编辑 PPTX

```python
from pathlib import Path
from utils.monthly_report_pptx import build_monthly_report_pptx

result = build_monthly_report_pptx(
    markdown=report_text,
    output_path=Path("outputs/ppt/2026年6月中国乘用车市场月报.pptx"),
    dataset_path=context.dataset_path,
    sheet_name=context.selected_sheet,
)
```

## 推荐 Web 端点

| 方法 | 路径 | 用途 |
| --- | --- | --- |
| GET | `/api/market-skill/status` | 查看版本、数据源和默认门禁 |
| POST | `/api/market-skill/validate` | 模型调用前预检 |
| POST | `/api/chat` | 运行市场 Agent |
| POST | `/api/ppt` | 通过门禁后生成 PPTX |

前端日志应展示真实阶段：数据选择、门禁、TOP15解析、证据加载、模型返回、输出门禁和PPTX生成，不能用虚构的演示日志代替实际执行。
