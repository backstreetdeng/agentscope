set -eu
docker inspect deploy-new-car-mcp-1 --format '{{range .Mounts}}{{println .Source .Destination .RW}}{{end}}'
docker exec deploy-new-car-mcp-1 python -c "import hashlib,market_data.new_car_server as m; print('new_car_module',m.__file__); print('sha256',hashlib.sha256(open(m.__file__,'rb').read()).hexdigest())"
