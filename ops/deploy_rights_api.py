"""Deprecated: superseded by ops/deploy_cloud_rights_data_api.py.

Phase-5 已把权益服务的 REST 与 MCP 拆成两个独立进程，不再由 8812 上的
cloud_rights.Auth 混合形态同时承载 MCP 与 /api/v1。请改用双服务部署：

  - price-rights-data-api.service (127.0.0.1:8815, MARKET_RIGHTS_BACKEND=mysql)
  - price-rights-mcp.service       (127.0.0.1:8812, 经 data-api 的协议适配)

源码推送由本地 ops/deploy_cloud_rights_data_api.py 完成（SFTP 上传完整 market_data
包），云端发布脚本为 ops/deploy_cloud_rights.sh。
"""
import sys

if __name__ == '__main__':
    print('deploy_rights_api.py 已废弃；请使用 ops/deploy_cloud_rights_data_api.py '
          '与 ops/deploy_cloud_rights.sh。')
    sys.exit(2 if '--deploy' in sys.argv else 0)