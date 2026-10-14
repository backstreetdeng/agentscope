set -eu
printf 'CRON COMMANDS WITH ARGUMENTS HIDDEN\n'
crontab -l 2>/dev/null | awk '!/^#/ && NF {print $1,$2,$3,$4,$5,$6,"[arguments hidden]"}'
printf '\nSOURCE CONTAINER MOUNTS\n'
docker inspect policycrawler-web --format '{{range .Mounts}}{{.Source}} -> {{.Destination}}{{println}}{{end}}'
printf '\nSOURCE CONTAINER WORKDIR AND ENTRYPOINT\n'
docker inspect policycrawler-web --format 'workdir={{.Config.WorkingDir}} image={{.Config.Image}}'
printf '\nSOURCE PYTHON FILES\n'
docker exec policycrawler-web sh -c 'find /app -maxdepth 3 -type f -name "*.py" | head -80'
printf '\nSOURCE SCHEDULE REFERENCES\n'
docker exec policycrawler-web sh -c 'grep -RInE "APScheduler|BackgroundScheduler|cron|schedule|add_job" /app --include="*.py" --exclude-dir=venv --exclude-dir=.venv | head -90' || true
