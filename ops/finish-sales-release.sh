set -eu
docker exec market-data-api-20261013 python -c "from pathlib import Path; names=['api_read_models.py','monthly_sales_read.py']; [compile((Path('/app/mcp/market_data')/name).read_text(),name,'exec') for name in names]; print('api_syntax_ok')"
docker exec deploy-new-car-mcp-1 python -c "from pathlib import Path; names=['api_read_models.py','monthly_sales_read.py','new_car_server.py']; [compile((Path('/app/mcp/market_data')/name).read_text(),name,'exec') for name in names]; print('mcp_syntax_ok')"
docker restart market-data-api-20261013 deploy-new-car-mcp-1
docker exec market-data-api-20261013 python -c "from market_data.api_read_models import new_car_sales; d=new_car_sales({'model':'理想i8','energy_type':'纯电动'});print('i8_months',len(d['items']),'total',d['total_sales'],'legacy_kept',d['legacy_months_retained']); assert len(d['items'])==15 and d['legacy_months_retained']==3"
