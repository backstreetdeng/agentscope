# 中国乘用车行业月报 Skill 安装包

这是从当前项目中提炼出的首个可迁移安装包预览版，版本为 `0.1.0`。它把月报能力拆成业务规则、运行时、业务 Profile、PPTX 渲染器、质量门禁和测试六部分，便于其他同事复制后改成自己的报告场景。

## 包含内容

| 部分 | 目录 | 用途 |
| --- | --- | --- |
| Skill 入口 | `SKILL.md` | 触发条件、标准流程和禁止事项 |
| 业务 Profile | `profiles/passenger_vehicle_monthly/` | 页面、口径、写作和质量规则 |
| 运行时载荷 | `payload/skills/market_analysis_skill/` | Excel 解析、门禁、TOP15 和证据上下文 |
| 外部证据适配 | `payload/skills/agent_reach/` | 通过 Agent Reach/Exa 获取公开资料 |
| PPTX 渲染器 | `payload/utils/monthly_report_pptx.py` | 将正文和数据写入可编辑母版 |
| 回归测试 | `payload/tests/`、`evals/` | 代码测试、触发测试和业务验收用例 |
| 安装与体检 | `install.ps1`、`scripts/` | 预览安装、冲突备份和包级校验 |

## 当前能力边界

- 支持按月份工作表读取业务展示型交叉表。
- 支持车型类别、车型级别、轿车、SUV、MPV 五页月报。
- 支持 TOP15 代表车型筛选、外部证据补充、MiniMax-M3 正文生成和输出门禁。
- 支持将正文写入业务母版，生成 PowerPoint 原生图表、表格和文本框。
- 当前新增页面仍需要实现一个解析器/渲染器处理函数；`page_specs.yaml` 已把扩展接口占好位置，但运行时尚未完全配置驱动化。
- 当前 Web 路由、Agent 构建和 MiniMax 模型配置属于宿主工程，不在安装包里直接覆盖。

## 目录结构

```text
month-skill/
├── SKILL.md
├── README.md
├── manifest.yaml
├── requirements.txt
├── install.ps1
├── config/
├── profiles/passenger_vehicle_monthly/
│   ├── profile.yaml
│   ├── page_specs.yaml
│   ├── quality_rules.yaml
│   ├── narrative_rules.md
│   ├── data_contract.md
│   ├── assets/
│   └── examples/
├── payload/
│   ├── skills/
│   ├── utils/
│   └── tests/
├── references/
├── scripts/
├── evals/
├── tests/
└── dist/
```

## 先看包，不安装

```powershell
cd E:\AI\data\envs\helloagent\myproject\skills\market-analysis-skill\month-skill
E:\AI\data\envs\helloagent\Scripts\python.exe .\scripts\validate_package.py
E:\AI\data\envs\helloagent\Scripts\python.exe .\scripts\inspect_profile.py
.\install.ps1 -TargetProject "E:\临时目录\agentscope-demo"
```

安装器默认只输出计划，不写目标工程。

## 安装到同事工程

目标工程建议已具备：

- Python 3.11；
- `agentscope==2.0.3`；
- 一个可工作的 AgentScope 项目入口；
- MiniMax-M3 或其他 OpenAI 兼容模型配置；
- 可选的 `mcporter`/Agent Reach 外部检索环境。

执行安装：

```powershell
.\install.ps1 `
  -TargetProject "E:\path\to\colleague-project" `
  -Python "E:\path\to\venv\Scripts\python.exe" `
  -Apply
```

若目标已有同名文件，安装器会停止。只有确认需要替换时才使用 `-Force`；替换前文件会备份到目标工程 `.market_monthly_skill_backups/`。

## 宿主工程接线

1. 把 `config/market_analysis.example.json` 中 `skills.market_analysis` 节点合并进宿主 `model_config/config.json`。
2. 将 `MarketAnalysisSkill.prepare(...)` 放在市场 Agent 调用前，将 `prompt_context` 注入系统提示或用户任务。
3. 模型返回后调用 `validate_report(...)`。
4. 门禁允许后调用 `build_monthly_report_pptx(...)`。
5. Web 界面可增加状态、预检、生成 PPTX 三个端点；示例见 `references/integration_agentscope_2_0_3.md`。

## 同事如何新增页面

不要直接把新页要求塞进一个超长提示词。一次完整扩展至少包含：

1. 在 `page_specs.yaml` 增加页面定义和数据字段；
2. 在数据源中增加对应维度，并更新 `data_contract.md`；
3. 在 PPTX 母版中增加可编辑页面；
4. 在解析器和渲染器中增加对应 handler；
5. 在 `narrative_rules.md` 增加标题和分析方法；
6. 在 `quality_rules.yaml` 增加内容与版式门禁；
7. 增加至少一个标准样例、一个失败样例和一个回归测试。

完整步骤见 `references/extension_guide.md`。

## 数据与安全

安装包包含业务母版和演示验数数据，用于内部验证。向 GitHub、外部供应商或公开渠道分享 ZIP 前，必须执行 `references/security_sharing_checklist.md`，确认模板、数据和专家案例允许外发。`.env`、API Key、真实用户数据和原始访谈资料永远不进入安装包。

## 版本定位

`0.1.0` 是“可查看、可试装、可二次开发”的内部预览版。它已打包当前生产链路，但还不是通用 PyPI 包，也不会自动修改宿主 Web 页面或模型配置。
