set -eu
cp /opt/market-mcp-deploy/sales-releases/20261014-v1/backup-api/api_read_models.py /opt/market-mcp-deploy/api-releases/20261013-v1/market_data/api_read_models.py
docker cp /opt/market-mcp-deploy/sales-releases/20261014-v1/backup-mcp/new_car_server.py deploy-new-car-mcp-1:/app/mcp/market_data/new_car_server.py
docker restart market-data-api-20261013 deploy-new-car-mcp-1
docker exec market-data-api-20261013 python -c "from market_data.api_read_models import new_car_sales; d=new_car_sales({'model':'理想i8'});print('restored_sales_months',len(d['items']))"
