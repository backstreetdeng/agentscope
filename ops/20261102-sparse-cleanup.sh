set -euo pipefail
rm -f /tmp/answers.csv /tmp/sparse_backfill.tsv /tmp/sparse_backfill.py
echo "cleaned tmp"
ls -la /tmp/answers.csv /tmp/sparse_backfill.tsv /tmp/sparse_backfill.py 2>&1 || echo "all removed"
