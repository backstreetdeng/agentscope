# 四大数据底座 MCP 最终部署说明

## 服务与工具

| MCP 插件 | 默认端口 | 生产路径 | 主要工具 |
|---|---:|---|---|
| `policy_mcp` | 8811 | `/mcp/policy` | 状态、检索、明细、变化、区域比较、Excel导出 |
| `rights_mcp` | 8812 | `/mcp/rights` | 状态、检索、有效权益、明细、车型比较、变化、Excel导出 |
| `new_car_mcp` | 8813 | `/mcp/new-car` | 状态、上市车型、规划车型、上市日历、销量、车型比较 |
| `reputation_mcp` | 8814 | `/mcp/reputation` | 状态、车型清单、摘要、标签树、评论检索、证据、车型比较 |

所有工具均为只读工具，并带有 MCP `readOnlyHint=true`、`destructiveHint=false`、
`idempotentHint=true` 和 `openWorldHint=false` 注解。

## 页面业务 API

`data-api` 与四个 MCP 服务读取同一套只读数据模型，但用于页面的确定性查询，避免页面加载时执行 MCP 初始化和工具发现。网关路径为：

```text
GET /api/v1/policy/overview
GET /api/v1/policies
GET /api/v1/policies/snapshot
POST /api/v1/policies/export
GET /api/v1/rights/overview
GET /api/v1/rights
POST /api/v1/rights/export
GET /api/v1/new-cars/*
GET /api/v1/reputation/*
```

这些接口使用与 MCP 相同的 Bearer Token；仅供服务端调用，浏览器不得保存该 Token。智能体的自然语言、跨域检索和解释任务继续调用 MCP。

权益 API 与原 MCP 共用腾讯云 8812 loopback 监听和 SSH 18812 通道，读取 MySQL `ledger`；146 API 不使用旧 PostgreSQL 权益台账。概览成功结果缓存60秒，并发请求合并；失败不缓存。页面侧复用 HTTP 连接池，证书初始化在线程中执行，不阻塞智能体事件循环。

筛选接口采用数据库分页；目前需要前端筛选的新车/规划/政策表格使用 `/snapshot` 在单个只读事务中读取完整、有版本的数据（上限10000条，超限报错）。新车明细按品牌/车型精确查询。政策导出校验记录编号与版本；权益导出沿用全部筛选条件、21列表头与5000条上限。

## 第一次部署到 192.168.3.146

1. 将 `myproject/mcp`、`myproject/assets/data` 上传至服务器相同相对目录。
2. 创建 PostgreSQL 只读运行账号及一次性导入账号。
3. 用导入账号执行 `deploy/sql/001_market_mcp.sql`。
4. 复制 `deploy/.env.example` 为 `deploy/.env`，填写数据库密码和随机 Token。
5. 临时使用有写权限的账号执行：

   ```bash
   cd /path/to/myproject/mcp
   MARKET_MCP_BACKEND=postgres python scripts/initialize_database.py
   ```

6. 将 `deploy/.env` 中的数据库账号切换为只读账号。
7. 启动：

   ```bash
   cd /path/to/myproject/mcp/deploy
   docker compose up -d --build
   docker compose ps
   docker compose logs --tail=100
   ```

生产访问地址默认为：

```text
http://192.168.3.146:8788/mcp/policy
http://192.168.3.146:8788/mcp/rights
http://192.168.3.146:8788/mcp/new-car
http://192.168.3.146:8788/mcp/reputation
```

正式使用时，应在现有企业网关上配置 HTTPS 内部域名，再把四条路径转发到 `8788`。

## AgentScope 接入

`agent_client.py` 已提供四个 `HttpMCPConfig` 客户端。智能体进程设置：

```text
MARKET_MCP_BASE_URL=http://192.168.3.146:8788
MARKET_MCP_API_TOKEN=<与服务端一致的Token>
```

代码中加载：

```python
import sys
sys.path.insert(0, "/path/to/myproject/mcp")
from agent_client import load_market_mcp_tools

tools = await load_market_mcp_tools()
```

创建市场战略智能体时传入这些远程工具：

```python
agent = build_market_strategy_agent(config, market_mcp_tools=tools)
```

## 本地开发

政策、权益默认使用现有 JSON 快照，无需数据库：

```powershell
cd myproject\mcp
$env:MCP_TRANSPORT='streamable-http'
python -m market_data.policy_server
```

生产环境设置 `MARKET_MCP_BACKEND=postgres` 后，政策、权益改从 PostgreSQL 读取；
新车和口碑始终读取现有 `vectordb` 表。

## 数据更新

- 政策/权益：生成新的 JSON 快照后重新运行 `import_policy_rights.py`；脚本按记录编号幂等更新。
- 新车：继续使用现有同步脚本写入 `new_car_model`、`planned_new_car` 和 `new_car_monthly_sales`。
- 口碑：继续使用现有口碑同步脚本写入 `new_car_reputation_taxonomy_summary` 与 `new_car_reputation_review_tag`。
- Excel 导出：写入共享卷 `mcp-exports`，通过受 Token 保护的 `/downloads/` 返回。

## 验证

```powershell
cd myproject
..\Scripts\python.exe -m unittest tests.test_market_data_mcp -v
```

部署后应使用 MCP Inspector 分别连接四个外部路径，确认工具发现、参数校验、分页和鉴权均正常。
