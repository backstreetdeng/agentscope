# AgentScope 2.0.3 乘用车市场与配置多智能体工程

本工程基于 Python AgentScope 2.0.3 稳定正式版，面向乘用车企业“市场战略机会决策 + 用户洞察配置定义”场景构建。当前阶段两个 Agent 独立工作，后续可扩展为上下游联动协作。

## 工程目录

```text
myproject/
├── .env
├── requirements.txt
├── model_config/
│   └── config.json
├── agents/
│   ├── __init__.py
│   ├── market_strategy_agent.py
│   └── user_insight_agent.py
├── tools/
│   ├── __init__.py
│   └── custom_tools.py
├── skills/
│   ├── anysearch/
│   │   ├── README.md
│   │   └── adapter.py
│   ├── market-analysis-skill/       # 业务原始 Skill、验数表和示例材料（只读保留）
│   └── market_analysis_skill/       # 可执行的市场月报分析 Skill
│       ├── runtime.py
│       ├── cli.py
│       ├── SKILL.md
│       ├── README.md
│       └── evals/
├── model_adapters/
│   ├── __init__.py
│   └── local_adapter.py
├── mcp/
│   ├── database/
│   ├── file_store/
│   ├── vector_store/
│   ├── bi/
│   └── research_platform/
├── data/
│   └── schemas/
├── utils/
│   ├── __init__.py
│   ├── config.py
│   ├── model_factory.py
│   └── text.py
├── app.py
├── main.py
├── README.md
└── doc/
```

## 各层职责

- `main.py`：命令行入口，只负责加载配置、多 Agent 调度、日志打印。
- `app.py`：本地 Web 演示入口，支持双 Agent 选择、Skill 演示、报告生成。
- `model_config/config.json`：模型、Agent、Demo 任务统一配置。
- `agents/`：所有自定义智能体定义，包含业务 Prompt 和 Agent 构建函数。
- `tools/`：自定义工具包，包含 AnySearch、web-fetch、Tavily、Playwright、agent-reach、用户标签工具。
- `skills/anysearch/`：AnySearch 工程内适配层，避免业务代码直接依赖用户目录路径。
- `skills/market-analysis-skill/`：业务同事提供的原始材料，作为方法论和验数数据审计依据，不由运行时改写。
- `skills/market_analysis_skill/`：将业务专家经验封装成可调用运行时，负责触发判断、Excel 解析、输入/输出门禁和报告上下文注入。
- `mcp/`：MCP 连接层占位，后续用于数据库、文件库、向量库、BI、调研平台。
- `data/`：市场与用户洞察数据资产规划，当前只放目录说明和标签体系。
- `model_adapters/`：自定义模型适配器二次开发示例。
- `utils/`：配置加载、模型工厂、文本清理等通用能力。

## 安装依赖

```powershell
cd E:\AI\data\envs\helloagent\Scripts
.\activate

cd E:\AI\data\envs\helloagent\myproject
pip install -r requirements.txt
```

如需使用动态网页抓取工具：

```powershell
playwright install chromium
```

## 环境变量

`.env` 至少需要：

```env
MINIMAX_MODEL_ID=MiniMax-M2.7-highspeed
MINIMAX_API_KEY=你的MiniMax中文平台Key
```

当前项目使用 MiniMax-M3 时，建议：

```env
MINIMAX_MODEL_ID=MiniMax-M3
```

`model_config/config.json` 中的 `providers.minimax.extra_body.reasoning_split` 已设为
`true`：兼容接口会把模型推理信息和最终正文分开，应用只向业务界面、报告与 PPT 传递
最终正文。

如需 Tavily 搜索：

```env
TAVILY_API_KEY=你的Tavily Key
```

如需 AnySearch 搜索：

```env
ANYSEARCH_API_KEY=你的AnySearch Key
```

MiniMax 中文平台默认端点：

```text
https://api.minimaxi.com/v1
```

## 运行命令行 Demo

```powershell
python main.py
```

程序会顺序运行：

1. 市场战略性机会决策智能体
2. 用户洞察与配置定义决策智能体

并在终端打印每个 Agent 的输入、输出和结果摘要。

## 启动 Web 业务界面

```powershell
python app.py
```

浏览器打开：

```text
http://127.0.0.1:7860/
```

Web 业务能力：

- 选择市场战略 Agent 或用户洞察 Agent。
- 点击 Skill 工具链按钮自动填入任务问题。
- 运行时展示进度条、阶段卡片、日志。
- 输出后可生成“汇报版”并下载 Markdown 报告。

## 市场月报分析 Skill

市场战略 Agent 新增“月报市场分析”可执行 Skill，用于把业务同事提供的
`SKILL-improved.md/.docx` 方法论落地为受数据约束的报告工作流，而不是单纯拼接 Prompt。

在网页中选择“市场分析”，再在分析类型下拉框选择“市场月报分析”；也可以在问题中使用
“月报、月度市场、车型类别、车型级别、销量结构”等词自动触发。执行链路如下：

```text
业务问题
  -> Skill 触发判定
  -> Excel 月报验数表解析
  -> 输入数据门禁（口径、周期、结构、趋势、竞争明细）
  -> 已验证数据和固定章节注入市场战略 Agent
  -> MiniMax-M3 生成报告
  -> 输出门禁（章节、来源、展望确定性、数据缺口）
  -> 前端执行日志、调试审计和报告/PPT 生成
```

默认数据集为 `skills/market-analysis-skill/1-5月报 AI验数.xlsx`。生产环境可在
`.env` 指向当月正式数据，避免改动代码：

```env
MARKET_ANALYSIS_DATA_PATH=E:\业务数据\2026年6月乘用车终端零售.xlsx
```

数据源优先级：本次调用指定路径 > `MARKET_ANALYSIS_DATA_PATH` >
`model_config/config.json` 的默认值 > 业务验数样本。

当前业务验数样本为展示型交叉表，能支撑车型类别/级别、同比/环比和结构变化判断；若要
生成正式的 TOP15、品牌集中度、区域策略或因果解释，必须补充车型销量、品牌归属、区域
渠道/库存和政策/新品事件等明细。Skill 会将这类不足标为“待补充”，不会用模型虚构数据。

### 本地调试与审计

不调用大模型、只验证默认 Excel 数据门禁：

```powershell
E:\AI\data\envs\helloagent\Scripts\python.exe -m skills.market_analysis_skill.cli --json
```

Web 调试接口：

- `GET /api/market-skill/status`：查看当前 Skill、默认数据源和输入门禁。
- `POST /api/market-skill/validate`：手动执行默认数据源的数据门禁。
- `GET /api/agent-run/latest`：查看最近一次执行的安全审计摘要、真实工具调用和 Skill 门禁结果；不返回 API Key 或完整系统提示词。

离线回归测试：

```powershell
E:\AI\data\envs\helloagent\Scripts\python.exe -m unittest discover -s tests -p test_market_analysis_skill.py -v
```

## 切换模型

修改 `model_config/config.json`：

```json
{
  "active_provider": "minimax"
}
```

可选 provider：

- `minimax`：MiniMax OpenAI 兼容接口。
- `local_ollama`：本地 Ollama 模型。
- `openai_compatible_cloud`：其他 OpenAI 兼容云模型。
- `custom_adapter_example`：自定义模型适配器示例。

## 新增智能体

1. 在 `agents/` 下新增文件，例如 `competitor_agent.py`。
2. 编写系统提示词和 `build_xxx_agent(config)`。
3. 复用稳定版写法：

```python
from agentscope.agent import Agent, ReActConfig
from agentscope.tool import Toolkit

from tools.custom_tools import build_business_toolkit
from utils.model_factory import build_model
```

4. 在 `main.py` 或 `app.py` 中接入新的 Agent 调度入口。

## 新增工具

在 `tools/custom_tools.py` 中继承 `ToolBase` 或 `ReadOnlyBusinessTool`，实现：

- `name`
- `description`
- `input_schema`
- `check_permissions`
- `call`

然后加入 `build_business_toolkit()`：

```python
def build_business_toolkit():
    return [
        AnySearchTool(),
        WebFetchTool(),
        YourNewTool(),
    ]
```

## 用户洞察自动打标签

当前工程已内置 `user_insight_tagger`，用于冷启动阶段处理：

- 用户访谈音频 ASR 转写稿
- 群访谈纪要
- 深访逐字稿
- 车主口碑评论
- 社媒评论

建议流程：

```text
音频/评论原文
  -> ASR 转写或文本清洗
  -> 隐私脱敏
  -> 片段切分
  -> user_insight_tagger 自动打标签
  -> 人工抽样复核
  -> 标签表/需求矩阵/向量索引
  -> 用户洞察 Agent 检索和分析
```

详细标签体系见 `data/schemas/user_insight_tagging.md`。

## MCP 扩展占位

`mcp/` 目录已经预留以下连接层：

- `database/`：销量库、价格库、车型配置库。
- `file_store/`：报告、PPT、Excel、访谈音频库。
- `vector_store/`：用户原声、评论、访谈转写稿、行业报告向量库。
- `bi/`：BI 看板和指标平台。
- `research_platform/`：访谈项目、问卷、受访者画像。

当前阶段建议由 `tools/` 中的 ToolBase 包装 MCP 调用，不让 Agent 直接依赖 MCP。

## 新增模型适配器

参考 `model_adapters/local_adapter.py`。

如果模型厂商兼容 OpenAI Chat Completions，建议继承 `OpenAIChatModel`。如果完全不兼容 OpenAI，再参考 AgentScope 2.0.3 文档实现更底层的模型类。

## 常见报错

### 1. `invalid api key`

MiniMax Key 与端点不匹配。中文平台 Key 使用：

```text
https://api.minimaxi.com/v1
```

不要和国际站常见端点混用：

```text
https://api.minimax.io/v1
```

### 2. `No module named agentscope`

虚拟环境未激活或依赖未安装：

```powershell
cd E:\AI\data\envs\helloagent\Scripts
.\activate
cd E:\AI\data\envs\helloagent\myproject
pip install -r requirements.txt
```

### 3. Playwright 不可用

```powershell
pip install -r requirements.txt
playwright install chromium
```

### 4. Tavily 未配置

在 `.env` 添加：

```env
TAVILY_API_KEY=你的Tavily Key
```

### 5. agent-reach CLI 未检测到

`agent_reach_search` 是本地 CLI 适配示例，需要系统 `PATH` 中存在 `agent-reach`。未安装时不影响主流程，只会返回提示。

## AgentScope 2.0.3 稳定版 API

本工程只使用以下稳定公开 API：

- `Agent`
- `ReActConfig`
- `OpenAIChatModel`
- `OllamaChatModel`
- `OpenAICredential`
- `OllamaCredential`
- `Toolkit`
- `ToolBase`
- `ToolChunk`
- `UserMsg`

未使用 AgentScope 2.0.4 dev 实验接口、临时参数或私有底层 API。
