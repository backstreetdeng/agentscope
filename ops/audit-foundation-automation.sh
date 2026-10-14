set -eu
docker ps --format '{{.Names}}|{{.Image}}|{{.Status}}|{{.Ports}}'
printf '\nPROJECT FILES\n'
find /opt/market-mcp-deploy -maxdepth 4 -type f ! -name '.env*' ! -path '*/assets/data/*' ! -path '*/__pycache__/*' | head -100
printf '\nROOT CRON TASK COUNTS\n'
crontab -l 2>/dev/null | awk '!/^#/ && NF {n++; if ($0 ~ /market|policy|new.car|reputation|rights/) m++} END {print "total=" n+0, "market_related=" m+0}'
printf '\nTIMER SERVICES\n'
systemctl list-timers --all --no-pager
printf '\nCANDIDATE SOURCE SERVICE DIRECTORIES\n'
find /opt -maxdepth 2 -type d | grep -Ei 'policy|crawler|market|reputation|car|koubei' | head -60
