"""BCI-007 报告版本：指纹规则升级到 report-fingerprint/2.0 + 软删除列。

背景
- 旧指纹把大纲版本与渲染器版本也算进数据指纹，导致大纲 2.0.0→2.1.0、渲染器 1.0.3→1.0.4
  之后所有历史版本被判「已过期」。
- 新规则只按数据身份取指纹（分析配置、档案模板、样本量、档案代次），
  大纲/渲染器只作为「可重新生成」提示。

本脚本做两件事（默认 dry-run，不改库）：
1. `bci.report_version` 增加 `deleted_at`（软删除），`--apply` 时执行 DDL；
2. 用每版保存的 `source_snapshot` 重算数据指纹并回填 `data_fingerprint`；
   数据与当前一致则把误判的 stale 恢复为 valid，不一致则保留 stale 并写入具体原因。

用法：
    ..\\Scripts\\python.exe -B ops/bci_report_fingerprint_v2.py            # 预演
    ..\\Scripts\\python.exe -B ops/bci_report_fingerprint_v2.py --apply    # 执行
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from competitor_insight.server import db  # noqa: E402
from competitor_insight.server.report_service import (  # noqa: E402
    FINGERPRINT_SCHEME,
    BciReportService,
)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true", help="真正写库；缺省只预演")
    args = parser.parse_args()

    service = BciReportService()
    print("fingerprint scheme:", FINGERPRINT_SCHEME)
    conn = db.connect(db.load_env())
    try:
        with conn.cursor() as cur:
            cur.execute(
                "select column_name from information_schema.columns "
                "where table_schema = 'bci' and table_name = 'report_version'"
            )
            columns = {row[0] for row in cur.fetchall()}
            has_deleted = "deleted_at" in columns
            print("deleted_at column:", "exists" if has_deleted else "missing")
            if args.apply and not has_deleted:
                cur.execute("alter table bci.report_version add column deleted_at timestamptz")
                conn.commit()
                print("DDL applied: bci.report_version.deleted_at")
                has_deleted = True

            cur.execute(
                """
                select v.report_version_id, r.model_key, v.version_label, v.status,
                       v.source_snapshot, v.data_fingerprint, v.content->>'outline_version'
                from bci.report_version v
                join bci.report r on r.report_id = v.report_id
                where r.legacy = false
                order by r.model_key, v.version_no
                """
            )
            rows = cur.fetchall()

            snapshots: dict[str, dict] = {}
            repaired = kept = skipped = 0
            for rid, model_key, label, status, source_snapshot, old_fp, outline in rows:
                if not source_snapshot:
                    print(f"  skip {label}: 无 source_snapshot，无法重算")
                    skipped += 1
                    continue
                if model_key not in snapshots:
                    snapshots[model_key] = service.snapshot([model_key])
                current = snapshots[model_key]
                new_fp = service.fingerprint(source_snapshot)
                data_same = new_fp == service.fingerprint(current)
                if data_same:
                    new_status, reason = "valid", ""
                    repaired += 1
                else:
                    new_status = "stale"
                    reason = service.data_reason(source_snapshot, current)
                    kept += 1
                flag = "valid" if data_same else "stale"
                print(f"  {model_key} {label} outline={outline} {status}->{new_status} {flag}"
                      + (f" ({reason})" if reason else ""))
                if args.apply:
                    cur.execute(
                        "update bci.report_version set data_fingerprint = %s, status = %s, "
                        "stale_reason = %s where report_version_id = %s",
                        (new_fp, new_status, reason, rid),
                    )
            if args.apply:
                conn.commit()
            print(f"done: repaired(valid)={repaired} stale={kept} skipped={skipped}"
                  f" apply={args.apply}")
            if not args.apply:
                print("dry-run：未改库。确认后用 --apply 执行。")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
