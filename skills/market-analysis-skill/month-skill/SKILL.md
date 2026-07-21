---
name: china-passenger-vehicle-monthly-report
description: >
  中国乘用车行业月报生成 Skill。用户要求基于月度销量 Excel 生成车型类别、车型级别、
  轿车/SUV/MPV 结构分析、TOP 车型原因解释、下月展望或可编辑 PPTX 时使用。适用于
  AgentScope 2.0.3 与 MiniMax-M3/OpenAI 兼容模型；先校验内部数据，再按需检索外部证据，
  最后执行文字报告和 PPTX 质量门禁。普通市场机会问答不要触发本 Skill。
---

# 中国乘用车行业月报

## 目标

把业务专家经验封装为可执行流程，而不是把 Excel 数字简单改写成文字。最终交付包括：

1. 可审计的 Markdown 月报正文；
2. 基于业务母版生成的 5 页可编辑 PPTX；
3. 输入门禁、输出门禁、证据清单和执行日志；
4. 可供同事新增页面、替换模板和适配数据源的业务 Profile。

## 使用顺序

1. 读取 `profiles/passenger_vehicle_monthly/profile.yaml`，确认数据口径和输出类型。
2. 按 `page_specs.yaml` 确认本次需要生成的页面，不要自行固定或删减页面。
3. 对输入 Excel 执行门禁：文件、月份、类别、级别、同比/环比、TOP15 和口径。
4. 优先使用内部销量、车型、新车、价格、政策和历史月报资料形成事实链。
5. 内部证据不足时，才通过 Agent Reach 等外部检索补充原因；外部摘要不能单独证明强因果。
6. 按 `narrative_rules.md` 写作：先给总体判断，再写代表车型，再解释机制，最后给小结或观察点。
7. 按 `quality_rules.yaml` 复核正文。未通过阻断项时不得生成正式 PPTX。
8. 使用 `utils.monthly_report_pptx.build_monthly_report_pptx` 写入可编辑母版并执行版式校验。

## 标准五页

- 2.1 车型类别：轿车、SUV、MPV、交叉型乘用车的结构分化。
- 2.2 车型级别：A00、A0、A、B、C+ 级市场迁移。
- 2.3 轿车级别：级别结构、代表车型与产品周期。
- 2.4 SUV 级别：级别结构、代表车型与竞争替代。
- 2.5 MPV 级别：场景需求、代表车型与换新窗口。

页面不是永久固定。新增页面时必须同步增加页面规格、数据契约、模板页、解析器、渲染器和回归测试，具体见 `references/extension_guide.md`。

## 强制写作规则

- 每页市场深度分析先写总体判断，再结合 2-3 个代表车型说明增长或下滑原因。
- 原因必须满足“内部数据变化 + 可追溯事件 + 时间范围一致”；否则标记为待核验假设。
- 正文直接针对车型和市场说话，不写“TOP15样本、候选、估算增减量”等内部过程词。
- 业务报告和 PPTX 不展示 `〔R1〕`、`〔E1〕` 等内部证据编号；来源仅保留在审计结果中。
- 正增长数值不显示 `+`；负增长保留 `-`。
- 不混用批发、零售、上险、交付口径，不凭空生成 CR5、品牌份额或政策影响。
- 只允许 AgentScope 2.0.3 稳定 API；不得加入 2.0.4 dev 参数或底层实验接口。

## 安装与检查

先预览安装清单：

```powershell
.\install.ps1 -TargetProject "E:\path\to\agentscope-project"
```

确认后执行：

```powershell
.\install.ps1 -TargetProject "E:\path\to\agentscope-project" -Apply
```

检查安装包自身：

```powershell
python .\scripts\validate_package.py
python .\scripts\inspect_profile.py
```

详细说明见 `README.md`。
