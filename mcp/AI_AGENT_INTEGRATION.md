# 四个市场数据 MCP 插件接入说明

## 已接入的独立插件

| 插件 ID | MCP 地址 | 工具前缀 | 主要用途 |
|---|---|---|---|
| `policy` | `/mcp/policy` | `policy_*` | 政策检索、明细、统计、导出 |
| `rights` | `/mcp/rights` | `rights_*` | 厂商权益、活动类型、优惠查询、导出 |
| `new-car` | `/mcp/new-car` | `new_car_*` | 新车、规划车型、销量和状态 |
| `reputation` | `/mcp/reputation` | `reputation_*` | 车型口碑、标签、评论和对比 |

四个插件分别建立 AgentScope `MCPClient`，单个插件不可用时只降级该插件，不影响其余插件和智能体本地工具。

## 本地配置

推荐直接双击项目根目录的 `配置四个MCP插件.cmd`，在安全输入框中填写服务器当前有效的新 Token。脚本会更新 `.env` 并验证四个端点，Token 不会显示在终端或写入命令历史。

也可以手工在项目根目录 `.env` 增加：

```dotenv
MARKET_MCP_BASE_URL=http://192.168.3.146:8790
MARKET_MCP_API_TOKEN=<服务器当前有效的新 Token>
```

可选的独立开关：

```dotenv
MARKET_MCP_POLICY_ENABLED=true
MARKET_MCP_RIGHTS_ENABLED=true
MARKET_MCP_NEW_CAR_ENABLED=true
MARKET_MCP_REPUTATION_ENABLED=true
```

业务配置在 `model_config/config.json` 的 `mcp_plugins` 节点。密钥只能放 `.env`，不能写入 JSON 或源码。

## 智能体运行方式

- Web 服务：`app.py` 在执行 `/api/chat` 时发现插件并把成功加载的 MCP 工具挂载到 AgentScope Toolkit。
- 命令行：`main.py` 会为市场 Agent 和用户洞察 Agent 分别加载插件。
- 默认启用全部四个插件；请求体可通过 `mcp_plugins` 只启用指定插件。

示例请求字段：

```json
{
  "agent": "market_strategy",
  "question": "结合地方置换政策和当前厂商权益，分析新能源 SUV 的机会窗口",
  "mcp_plugins": ["policy", "rights"]
}
```

## 状态检查

启动本地 Web 服务后访问：

```text
GET http://127.0.0.1:7860/api/mcp-plugins
```

返回每个插件的 `ready / disabled / misconfigured / unavailable` 状态、工具数量和工具名称，不返回 Token。

首页“数据底座 / Plugins 管理”会读取该接口显示真实连接状态；从首页调用 Agent 时，当前选中的插件会传入工作台。

## 验收标准

1. `/api/mcp-plugins` 显示 `ready=4`。
2. 政策、权益、新车、口碑四项均有独立工具列表。
3. 任意停用一个插件后，其余三个仍可挂载。
4. 智能体分析响应包含 `mcp_plugins` 状态摘要和插件加载审计事件。
