# 市场月报分析 Skill

该目录是可执行的生产运行时；默认业务 Profile 保存在
`profiles/passenger_vehicle_monthly/`。业务原始材料不在运行时改写，既保留审计依据，
也避免 Python 因目录名中的连字符而无法稳定导入。

## 已落地能力

- 支持显式选择或按问题关键词自动触发。
- 支持读取按月 Sheet 的展示型 `.xlsx` 交叉表，保留车型类别、车型级别、同比、环比等业务语义。
- 先执行数据门禁，再把已验证摘要和写作规范传给 MiniMax-M3。
- 对缺少车型/品牌明细的场景显式披露数据缺口，防止生成虚构 TOP15、CR5、品牌集中度。
- Agent 回答后复核固定章节、来源标注、展望确定性和数据缺口，并把真实执行事件返回前端日志。

## 配置数据源

默认演示数据源配置在 `model_config/config.json`：

```json
{
  "skills": {
    "market_analysis": {
      "enabled": true,
      "auto_trigger": true,
      "default_dataset": "skills/market_analysis_skill/profiles/passenger_vehicle_monthly/assets/demo_monthly_data.xlsx"
    }
  }
}
```

生产环境建议在 `.env` 设置，不提交到 Git：

```env
MARKET_ANALYSIS_DATA_PATH=E:\\业务数据\\2026年6月乘用车终端零售.xlsx
```

数据源优先级：本次调用指定路径 > `MARKET_ANALYSIS_DATA_PATH` > 配置默认值 > 业务验数样本。

## 调试命令

```powershell
cd E:\AI\data\envs\helloagent\myproject
E:\AI\data\envs\helloagent\Scripts\python.exe -m skills.market_analysis_skill.cli --json
```

指定文件校验：

```powershell
E:\AI\data\envs\helloagent\Scripts\python.exe -m skills.market_analysis_skill.cli `
  --input "E:\\业务数据\\2026年6月乘用车终端零售.xlsx"
```

Web 服务可查询状态：`GET /api/market-skill/status`；可执行默认数据门禁：`POST /api/market-skill/validate`。

## 输入数据升级建议

当前验数表适合验证月报页面中的结构数据。若希望自动补齐正式月报的 TOP15、品牌集中度、区域差异和政策驱动，需要另外提供：

- 车型月度终端零售明细：月份、车型、品牌、企业、能源类型、级别、车型类别、销量、同比、环比、区域。
- 品牌/企业归属表与车型生命周期表：支持品牌集中度、产品换代和新品放量判断。
- 区域销量与渠道/库存数据：支持区域策略和产能调配。
- 政策、新品、油价、促销等事件表：支持对异常波动形成可验证的原因解释。
