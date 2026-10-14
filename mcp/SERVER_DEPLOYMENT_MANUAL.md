# 192.168.3.146 四大数据底座 MCP 部署手册

本手册面向无法通过 SSH 自动发布、需要人工将部署包上传到服务器的场景。

## 1. 部署结果

部署完成后，AI 智能体通过以下地址调用：

```text
政策：http://192.168.3.146:8790/mcp/policy
权益：http://192.168.3.146:8790/mcp/rights
新车：http://192.168.3.146:8790/mcp/new-car
口碑：http://192.168.3.146:8790/mcp/reputation
```

四个地址均要求请求头：

```text
Authorization: Bearer <MCP_API_TOKEN>
```

默认使用 `8790`，因为检查发现服务器的 `8788` 已有进程监听。如已确认8790也被占用，修改
`deploy/.env` 中的 `MCP_GATEWAY_PORT` 即可。

## 2. 服务器前置条件

服务器需要：

- Linux x86_64；
- Docker Engine 24或更高版本；
- Docker Compose v2；
- 能访问本机或内网的 `192.168.3.146:5432/vectordb`；
- 至少2GB可用内存、5GB可用磁盘；
- 防火墙放行AI智能体所在网络访问选定的网关端口。

检查：

```bash
docker --version
docker compose version
ss -lntp | grep -E ':8788|:8790'
```

## 3. 上传和解压

把 `market-mcp-deploy-20260929.zip` 上传到服务器，例如 `/opt`，然后执行：

```bash
cd /opt
unzip market-mcp-deploy-20260929.zip
cd market-mcp-deploy/mcp/deploy
```

解压后的关键结构：

```text
market-mcp-deploy/
├── assets/data/
│   ├── policy-intelligence.json
│   └── rights-intelligence.json
└── mcp/
    ├── market_data/
    ├── scripts/
    └── deploy/
```

## 4. 配置

```bash
cp .env.example .env
vi .env
```

第一次初始化数据库时，`MARKET_PG_USER` 和 `MARKET_PG_PASSWORD` 必须填写一个对
`vectordb` 具有建表权限的账号。必须修改：

```text
MCP_API_TOKEN=<至少32位随机字符串>
MCP_GATEWAY_PORT=8790
MARKET_PG_HOST=192.168.3.146
MARKET_PG_DATABASE=vectordb
MARKET_PG_USER=<首次部署使用的建表账号>
MARKET_PG_PASSWORD=<数据库密码>
MARKET_MCP_EXPORT_BASE_URL=http://192.168.3.146:8790/downloads
```

可生成随机Token：

```bash
openssl rand -hex 32
```

保护配置文件：

```bash
chmod 600 .env
```

## 5. 构建并启动

```bash
chmod +x deploy.sh
./deploy.sh
```

也可以手工执行：

```bash
docker compose config
docker compose up -d --build
docker compose ps
```

应看到五个服务：

```text
policy-mcp
rights-mcp
new-car-mcp
reputation-mcp
gateway
```

## 6. 第一次初始化数据库

仅首次部署或政策/权益表尚未创建时执行：

```bash
docker compose run --rm policy-mcp python scripts/initialize_database.py
```

该命令会执行四件事：

1. 创建或升级政策、权益结构化表；
2. 幂等导入1085条政策和272条权益；
3. 核验现有新车表；
4. 核验现有口碑标签及评论证据表。

成功结果应类似：

```json
{
  "schema": "ready",
  "imported": {"policy": 1085, "rights": 272},
  "domains": {
    "policy": {"action": "created_or_updated"},
    "rights": {"action": "created_or_updated"},
    "new_car": {"action": "existing_tables_reused"},
    "reputation": {"action": "existing_tables_reused"}
  }
}
```

然后将 `.env` 的数据库账号改成只读账号，并重启四个服务：

```bash
docker compose up -d --force-recreate policy-mcp rights-mcp new-car-mcp reputation-mcp
```

只读账号至少需要以下权限：

```sql
GRANT CONNECT ON DATABASE vectordb TO market_mcp_reader;
GRANT USAGE ON SCHEMA public TO market_mcp_reader;
GRANT SELECT ON market_dataset_meta, policy_record, rights_record,
  new_car_model, planned_new_car, new_car_monthly_sales,
  new_car_reputation_taxonomy_summary, new_car_reputation_review_tag
TO market_mcp_reader;
```

如果暂时没有独立只读账号，可以先使用现有数据库账号完成验证，但正式运行前应切换。

## 7. 验收四个 MCP

在一台装有Python和项目依赖的电脑上执行：

```bash
python mcp/scripts/verify_deployment.py \
  --base-url http://192.168.3.146:8790 \
  --token '<MCP_API_TOKEN>'
```

预期：

```text
policy: OK (6 tools)
rights: OK (7 tools)
new-car: OK (7 tools)
reputation: OK (7 tools)
```

查看服务日志：

```bash
cd /opt/market-mcp-deploy/mcp/deploy
docker compose logs --tail=100 policy-mcp
docker compose logs --tail=100 rights-mcp
docker compose logs --tail=100 new-car-mcp
docker compose logs --tail=100 reputation-mcp
docker compose logs --tail=100 gateway
```

如果网关日志出现以下错误：

```text
could not build map_hash, you should increase map_hash_bucket_size
```

确认 `deploy/nginx/default.conf.template` 在 `map` 指令前包含：

```nginx
map_hash_bucket_size 128;
```

然后仅重建网关容器：

```bash
docker compose up -d --force-recreate gateway
```

## 8. AI智能体配置

在AI智能体运行环境设置：

```text
MARKET_MCP_BASE_URL=http://192.168.3.146:8790
MARKET_MCP_API_TOKEN=<与服务器一致的Token>
```

AgentScope加载方式：

```python
import sys
sys.path.insert(0, "/path/to/myproject/mcp")

from agent_client import load_market_mcp_tools
from agents.market_strategy_agent import build_market_strategy_agent

mcp_tools = await load_market_mcp_tools()
agent = build_market_strategy_agent(config, market_mcp_tools=mcp_tools)
```

## 9. 日常更新

政策、权益JSON更新后，将两个JSON文件替换到 `assets/data`，执行：

```bash
cd /opt/market-mcp-deploy/mcp/deploy
docker compose run --rm policy-mcp python scripts/import_policy_rights.py
```

新车与口碑继续由现有同步任务写入 PostgreSQL，无需重新构建 MCP 镜像。

代码更新时：

```bash
docker compose up -d --build
```

## 10. 停止与回滚

停止服务但保留导出文件卷：

```bash
docker compose down
```

不要使用 `docker compose down -v`，否则会删除 MCP 导出文件卷。

代码回滚时，保留上一版部署目录，执行：

```bash
cd /opt/market-mcp-deploy-backup/mcp/deploy
docker compose up -d --build
```

数据库导入使用记录编号幂等更新，但回滚代码不会自动回滚数据库内容；如需数据回滚，应提前备份
`market_dataset_meta`、`policy_record` 和 `rights_record`。

## 11. 常见问题

### 返回401

AI智能体Token与服务器 `.env` 中的 `MCP_API_TOKEN` 不一致。

### 新车或口碑显示数据库不可用

检查数据库地址、账号权限，以及容器到 `192.168.3.146:5432` 的网络连通性：

```bash
docker compose exec new-car-mcp python -c \
  "from market_data.shared import query_scalar; print(query_scalar('SELECT 1'))"
```

如果初始化输出 `select_permission_required` 或日志出现 `permission denied for table
new_car_model`，表示当前 `vectordb` 用户可以连接数据库，但不是这些既有表的所有者，也没有
`SELECT` 权限。这不会回滚政策和权益导入，但新车、口碑 MCP 无法直接查询这些表。

不需要创建新用户；需要由表所有者或管理员对现有用户授权：

```sql
GRANT SELECT ON new_car_model, planned_new_car, new_car_monthly_sales,
  new_car_reputation_taxonomy_summary, new_car_reputation_review_tag
TO vectordb;
```

如果没有任何可执行 `GRANT` 的账号，只能暂时关闭新车、口碑 MCP，或后续改为调用已有的
新车/口碑 HTTP 服务，无法由容器绕过 PostgreSQL 权限。

### 镜像构建时pip下载较慢

部署包默认使用阿里云PyPI镜像。可在 `.env` 修改：

```text
PIP_INDEX_URL=https://mirrors.aliyun.com/pypi/simple/
```

如果构建卡在拉取 `python:3.11-slim` 或 `nginx`，需要配置 Docker Hub 镜像加速；PyPI
配置只影响 `pip install`。

### 端口冲突

修改 `.env`：

```text
MCP_GATEWAY_PORT=8791
MARKET_MCP_EXPORT_BASE_URL=http://192.168.3.146:8791/downloads
```

然后执行：

```bash
docker compose up -d --force-recreate gateway
```
