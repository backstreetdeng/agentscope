set -eu
docker inspect market-data-api-20261013 --format '{{range .Mounts}}{{println .Source .Destination}}{{end}}'
docker exec market-data-api-20261013 python -c "import hashlib,market_data.api_read_models as m; print('read_model_file',m.__file__); print('read_model_sha256',hashlib.sha256(open(m.__file__,'rb').read()).hexdigest())"
